"""Compare local models against fixed structural and content quality gates."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import sys
import time

import mlx.core as mx
from mlx_lm import generate, load
from mlx_lm.sample_utils import make_logits_processors, make_sampler

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from italix.pr_summary import (
    MAX_GENERATION_TOKENS,
    REPETITION_CONTEXT_SIZE,
    REPETITION_PENALTY,
    SYSTEM_PROMPT,
)

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "before", "by", "for",
    "from", "in", "is", "it", "of", "on", "only", "or", "the", "their",
    "this", "to", "when", "with", "without", "under", "into",
}


def words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9_]+", text.lower())


def content_words(text: str) -> set[str]:
    return {word for word in words(text) if word not in STOPWORDS and len(word) > 2}


def repeated_ngram_ratio(text: str, size: int = 4) -> float:
    sequence = words(text)
    ngrams = [tuple(sequence[i : i + size]) for i in range(len(sequence) - size + 1)]
    if not ngrams:
        return 0.0
    counts = Counter(ngrams)
    repeats = sum(count - 1 for count in counts.values() if count > 1)
    return repeats / len(ngrams)


parser = argparse.ArgumentParser()
parser.add_argument("--model", required=True)
parser.add_argument(
    "--candidate",
    action="append",
    required=True,
    help="NAME=BASE or NAME=/path/to/adapter-directory",
)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()

rubric = json.loads(Path("training/validation_rubric.json").read_text())
rows = [json.loads(line) for line in Path("data/valid.jsonl").read_text().splitlines()]
if len(rows) != len(rubric["examples"]):
    raise SystemExit("Validation rows and rubric entries differ")

sampler = make_sampler(temp=0.0)
processors = make_logits_processors(
    repetition_penalty=REPETITION_PENALTY,
    repetition_context_size=REPETITION_CONTEXT_SIZE,
)
results = {
    "policy": {
        "temperature": 0.0,
        "max_tokens": MAX_GENERATION_TOKENS,
        "repetition_penalty": REPETITION_PENALTY,
        "repetition_context_size": REPETITION_CONTEXT_SIZE,
        "rubric": rubric,
    },
    "candidates": [],
}

for spec in args.candidate:
    name, adapter = spec.split("=", 1)
    adapter_path = None if adapter == "BASE" else adapter
    model, tokenizer = load(args.model, adapter_path=adapter_path)
    candidate = {"name": name, "adapter": adapter, "examples": []}
    for row, criteria in zip(rows, rubric["examples"]):
        prompt = tokenizer.apply_chat_template(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                row["messages"][0],
            ],
            tokenize=False,
            add_generation_prompt=True,
        )
        started = time.perf_counter()
        response = generate(
            model,
            tokenizer,
            prompt=prompt,
            max_tokens=MAX_GENERATION_TOKENS,
            sampler=sampler,
            logits_processors=processors,
            verbose=False,
        ).strip()
        mx.synchronize()
        heading_counts = {
            heading: response.count(heading) for heading in rubric["required_headings"]
        }
        positions = [response.find(heading) for heading in rubric["required_headings"]]
        format_ok = all(count == 1 for count in heading_counts.values()) and positions == sorted(positions)
        repetition_ratio = repeated_ngram_ratio(response)
        repetition_ok = repetition_ratio <= rubric["max_repeated_ngram_ratio"]
        lowered = response.lower()
        concepts = [
            any(term in lowered for term in alternatives)
            for alternatives in criteria["required_concepts"]
        ]
        forbidden_hits = [term for term in criteria["forbidden_phrases"] if term in lowered]
        target = row["messages"][1]["content"]
        target_tokens = content_words(target)
        recall = len(content_words(response) & target_tokens) / len(target_tokens)
        content_ok = all(concepts) and not forbidden_hits and recall >= rubric["minimum_target_content_recall"]
        passed = format_ok and repetition_ok and content_ok
        candidate["examples"].append(
            {
                "id": criteria["id"],
                "response": response,
                "format_ok": format_ok,
                "heading_counts": heading_counts,
                "repetition_ratio": repetition_ratio,
                "repetition_ok": repetition_ok,
                "required_concepts_present": concepts,
                "forbidden_hits": forbidden_hits,
                "target_content_recall": recall,
                "content_ok": content_ok,
                "automatic_pass": passed,
                "seconds": time.perf_counter() - started,
            }
        )
    candidate["automatic_pass"] = all(item["automatic_pass"] for item in candidate["examples"])
    results["candidates"].append(candidate)
    del model, tokenizer
    mx.clear_cache()

args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
for candidate in results["candidates"]:
    scores = [item["automatic_pass"] for item in candidate["examples"]]
    print(f"{candidate['name']}: {sum(scores)}/{len(scores)} examples pass; overall={candidate['automatic_pass']}")
    for item in candidate["examples"]:
        print(
            f"  {item['id']}: format={item['format_ok']} repetition={item['repetition_ok']} "
            f"content={item['content_ok']} recall={item['target_content_recall']:.2f}"
        )
