"""Frozen server-compatible evaluation for change-triage candidates."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import time

import mlx.core as mx
from mlx_lm import generate, load
from mlx_lm.sample_utils import make_sampler

from italix.change_triage import COMPACT_PROMPT, MAX_GENERATION_TOKENS, PRODUCTION_PROMPT
from italix.engines import cached_qwen_path


def score(raw: str, expected: str) -> dict:
    format_ok = raw.strip() == expected
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = None
    target = json.loads(expected)
    fields = {
        key: bool(isinstance(parsed, dict) and parsed.get(key) == value)
        for key, value in target.items()
    }
    exact = format_ok and all(fields.values()) and list(parsed or {}) == list(target)
    return {"passed": exact, "format_ok": format_ok, "field_accuracy": fields}


def run_variant(name, rows, system_prompt, adapter_path=None):
    model, tokenizer = load(str(cached_qwen_path()), adapter_path=adapter_path)
    results, prompt_tokens = [], []
    started = time.perf_counter()
    for index, row in enumerate(rows, 1):
        user = row["messages"][-2]
        messages = [{"role": "system", "content": system_prompt}, user]
        prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        prompt_tokens.append(len(tokenizer.encode(prompt)))
        response = generate(
            model, tokenizer, prompt=prompt, max_tokens=MAX_GENERATION_TOKENS,
            sampler=make_sampler(temp=0.0), verbose=False,
        ).strip()
        result = score(response, row["messages"][-1]["content"])
        result.update({"index": index, "response": response, "expected": row["messages"][-1]["content"]})
        results.append(result)
    duration = time.perf_counter() - started
    del model, tokenizer
    mx.clear_cache()
    return {
        "name": name, "adapter_path": adapter_path, "passed": sum(x["passed"] for x in results),
        "total": len(results), "average_prompt_tokens": sum(prompt_tokens) / len(prompt_tokens),
        "duration_seconds": duration, "examples": results,
    }


def evaluate(split: str, adapters: list[tuple[str, str]], output: Path):
    rows = [json.loads(line) for line in Path(f"data/change_triage/{split}.jsonl").read_text().splitlines()]
    candidates = [
        run_variant("base_compact", rows, COMPACT_PROMPT),
        run_variant("base_production_scaffold", rows, PRODUCTION_PROMPT),
    ]
    candidates.extend(run_variant(name, rows, COMPACT_PROMPT, path) for name, path in adapters)
    scaffold = candidates[1]
    for candidate in candidates[2:]:
        candidate["qualified"] = (
            candidate["passed"] == candidate["total"]
            and candidate["passed"] >= scaffold["passed"]
            and candidate["average_prompt_tokens"] <= scaffold["average_prompt_tokens"] * 0.40
        )
    payload = {
        "workload": "change_triage", "split": split,
        "gate": {"exact_pass_rate": 1.0, "quality_at_least_scaffold": True, "maximum_prompt_token_ratio": 0.40},
        "candidates": candidates,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n")
    for item in candidates:
        print(f"{item['name']}: {item['passed']}/{item['total']}, avg prompt {item['average_prompt_tokens']:.1f}")
    return payload


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=["valid", "holdout"], default="valid")
    parser.add_argument("--adapter", action="append", default=[], help="name=path")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    adapters = [tuple(value.split("=", 1)) for value in args.adapter]
    evaluate(args.split, adapters, args.output)


if __name__ == "__main__":
    main()
