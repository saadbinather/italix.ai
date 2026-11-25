"""Opt-in change-triage objectives for the local MLX-LM LoRA CLI."""

from functools import partial
import json
import math
import re
from pathlib import Path
from unittest.mock import patch

import mlx.core as mx
import mlx.nn as nn
from mlx_lm import lora
from mlx_lm.tokenizer_utils import TokenizerWrapper
from mlx_lm.tuner.datasets import ChatDataset
from mlx_lm.tuner.trainer import default_loss, iterate_batches, train

OBJECTIVE_VERSION = "risk_token_weighted_v1"
CLASSIFICATION_VERSION = "risk_classification_v1"
RISK_CLASSES = ("low", "medium", "high")
_RISK_STRING = re.compile(r'"risk"\s*:\s*"((?:[^"\\]|\\.)*)"')


def objective_weight(objective: dict) -> float:
    if objective.get("name") != OBJECTIVE_VERSION:
        raise ValueError("Unsupported training objective")
    weight = float(objective["risk_token_weight"])
    if not math.isfinite(weight) or weight <= 0:
        raise ValueError("Risk token weight must be positive and finite")
    return weight


def risk_token_span(tokenizer, row, tokens, offset):
    """Return target token indices overlapping the risk value inside the final answer."""
    messages = row["messages"]
    answer = messages[-1]["content"]
    matches = list(_RISK_STRING.finditer(answer))
    parsed = json.loads(answer)
    if (messages[-1]["role"] != "assistant" or not isinstance(parsed, dict)
            or not isinstance(parsed.get("risk"), str) or len(matches) != 1):
        raise ValueError("Expected one string risk value in the final assistant object")
    template = {"tools": row.get("tools"), "tokenize": False}
    prompt = tokenizer.apply_chat_template(messages[:-1], add_generation_prompt=True, **template)
    rendered = tokenizer.apply_chat_template(messages, **template)
    if not rendered.startswith(prompt + answer):
        raise ValueError("Assistant answer does not follow the rendered prompt")
    # MLX-LM forwards normal attributes but does not forward Python's call protocol.
    offset_tokenizer = tokenizer._tokenizer if isinstance(tokenizer, TokenizerWrapper) else tokenizer
    encoded = offset_tokenizer(rendered, add_special_tokens=False, return_offsets_mapping=True)
    if list(encoded["input_ids"]) != list(tokens):
        raise ValueError("Offset tokenization differs from the training chat template")
    start, end = matches[0].span(1)
    start, end = start + len(prompt), end + len(prompt)
    indices = [index for index, (left, right) in enumerate(encoded["offset_mapping"])
               if left < end and right > start and left < right]
    if not indices or indices[0] < offset or indices != list(range(indices[0], indices[-1] + 1)):
        raise ValueError("Risk value has no contiguous supervised token span")
    return indices[0], indices[-1] + 1


def classification_targets(dataset, row, tokens, offset):
    """Verify shared-prefix single-token class alternatives in the actual template."""
    answer = row["messages"][-1]["content"]
    match = _RISK_STRING.search(answer)
    start, end = risk_token_span(dataset.tokenizer, row, tokens, offset)
    class_ids = []
    for label in RISK_CLASSES:
        replacement = answer[:match.start(1)] + label + answer[match.end(1):]
        alternative = {**row, "messages": [*row["messages"][:-1], {"role": "assistant", "content": replacement}]}
        candidate, candidate_offset = dataset.process(alternative)
        left, right = risk_token_span(dataset.tokenizer, alternative, candidate, candidate_offset)
        if (candidate_offset != offset or left != start or right != end or right - left != 1
                or candidate[:left] != tokens[:start] or candidate[right:] != tokens[end:]
                or dataset.tokenizer.decode(candidate[left:right]) != label):
            raise ValueError("Risk classification v1 needs single-token labels with an identical context")
        class_ids.append(candidate[left])
    target = RISK_CLASSES.index(json.loads(answer)["risk"])
    if len(set(class_ids)) != 3 or class_ids[target] != tokens[start]:
        raise ValueError("Risk class tokens do not uniquely identify the supervised target")
    return (start, target, *class_ids)


def prepare_spans(dataset: ChatDataset, max_seq_length: int, *, classification=False):
    if not isinstance(dataset, ChatDataset) or not dataset.mask_prompt:
        raise ValueError("Risk weighting requires a chat dataset with assistant masking")
    spans = {}
    for index in range(len(dataset)):
        row = dataset[index]
        tokens, offset = dataset.process(row)
        if len(tokens) > max_seq_length:
            raise ValueError("Weighted training requires examples to fit the sequence limit")
        span = (classification_targets(dataset, row, tokens, offset) if classification
                else risk_token_span(dataset.tokenizer, row, tokens, offset))
        key = (offset, tuple(tokens))
        if key in spans and spans[key] != span:
            raise ValueError("Identical token sequence has conflicting risk spans")
        spans[key] = span
    return spans


def weighted_cross_entropy(model, batch, lengths, risk_spans, *, weight):
    targets = batch[:, 1:]
    positions = mx.arange(1, targets.shape[1] + 1)
    active = (positions >= lengths[:, :1]) & (positions <= lengths[:, 1:])
    risk = (positions >= risk_spans[:, :1]) & (positions < risk_spans[:, 1:])
    weights = mx.where(active, mx.where(risk, weight, 1.0), 0.0).astype(mx.float32)
    ce = nn.losses.cross_entropy(model(batch[:, :-1]), targets).astype(mx.float32)
    return (ce * weights).sum() / weights.sum(), active.sum()


def risk_loss(model, batch, lengths, risk_spans=None, *, weight):
    if risk_spans is None:
        return default_loss(model, batch, lengths)
    return weighted_cross_entropy(model, batch, lengths, risk_spans, weight=weight)


def classification_components(model, batch, lengths, decision):
    targets = batch[:, 1:]
    positions = mx.arange(1, targets.shape[1] + 1)
    active = (positions >= lengths[:, :1]) & (positions <= lengths[:, 1:])
    logits = model(batch[:, :-1])
    count = active.sum()
    sft = (nn.losses.cross_entropy(logits, targets) * active).astype(mx.float32).sum() / count
    class_logits = logits[mx.arange(batch.shape[0]), decision[:, 0] - 1]
    scores = mx.take_along_axis(class_logits, decision[:, 2:], axis=1).astype(mx.float32)
    risk = nn.losses.cross_entropy(scores, decision[:, 1]).mean()
    return sft, risk, count


def classification_loss(model, batch, lengths, decision=None, *, coefficient):
    if decision is None or coefficient == 0:
        return default_loss(model, batch, lengths)
    sft, risk, count = classification_components(model, batch, lengths, decision)
    return sft + coefficient * risk, count


def weighted_batches(*, spans, loop=False, **kwargs):
    # Delegate ordering, padding and distributed slicing to MLX-LM.
    for batch, lengths in iterate_batches(loop=loop, **kwargs):
        if not loop:
            yield batch, lengths  # Periodic validation uses ordinary CE.
            continue
        ranges = [spans[(offset, tuple(tokens[:length]))]
                  for tokens, (offset, length) in zip(batch.tolist(), lengths.tolist(), strict=True)]
        yield batch, lengths, mx.array(ranges)


def main():
    # Use the stock CLI for setup, optimizer, callbacks and checkpoint format.
    def run(args, *positional, **options):
        objective = getattr(args, "training_objective", None)
        if objective is None or objective.get("name") == "standard":
            return stock_run(args, *positional, **options)
        classification = objective.get("name") == CLASSIFICATION_VERSION
        if classification:
            coefficient = float(objective["lambda"])
            if not math.isfinite(coefficient) or coefficient < 0:
                raise ValueError("Classification lambda must be finite and nonnegative")
            if coefficient == 0:
                return stock_run(args, *positional, **options)
            loss = partial(classification_loss, coefficient=coefficient)
        else:
            loss = partial(risk_loss, weight=objective_weight(objective))
        if not Path(args.model).is_dir() or not Path(args.data).is_dir() or args.report_to or args.test:
            raise ValueError("Weighted recipe requires local inputs and standalone validation")
        if (Path(args.data) / "test.jsonl").exists():
            raise ValueError("Keep held-out test data outside the training directory")
        spans = {}

        def load_with_spans(config, tokenizer):
            datasets = stock_load(config, tokenizer)
            spans.update(prepare_spans(datasets[0], args.max_seq_length, classification=classification))
            print(f"Objective {objective}; verified risk targets={len(spans)}", flush=True)
            return datasets

        def train_with_weights(**kwargs):
            return train(**kwargs, loss=loss,
                         iterate_batches=partial(weighted_batches, spans=spans))

        # Scoped to this CLI invocation. No installed files are changed.
        with patch.object(lora, "load_dataset", load_with_spans), patch.object(lora, "train", train_with_weights):
            return stock_run(args, *positional, **options)

    stock_run, stock_load = lora.run, lora.load_dataset
    with patch.object(lora, "run", run):
        lora.main()


if __name__ == "__main__":
    main()
