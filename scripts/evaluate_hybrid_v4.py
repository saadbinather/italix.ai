"""Evaluate the separate hybrid PR-summary pipeline on v4 development data."""

from __future__ import annotations

import json
from pathlib import Path
import statistics
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from italix.engines import LocalMLXEngine
from italix.evaluation import score_response
from italix.hybrid_pr_summary import HybridPRSummarizer


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data/v4/independent_valid.jsonl"
BASELINE = ROOT / "artifacts/experiments/pr-summary-v4-r4-seed149-20261020/evaluation.json"
OUTPUT = ROOT / "artifacts/experiments/pr-summary-v4-r4-seed149-20261020/hybrid_evaluation.json"

rows = [json.loads(line) for line in SOURCE.read_text().splitlines()]
baseline = json.loads(BASELINE.read_text())
hybrid = HybridPRSummarizer(LocalMLXEngine())
examples = []
for index, row in enumerate(rows, 1):
    user = row["messages"][-2]["content"]
    diff = user.split("\n\n", 1)[-1]
    expected = row["messages"][-1]["content"]
    result = hybrid.summarize(diff)
    score = score_response(result.summary, expected, diff)
    examples.append({
        "index": index,
        "passed": score["passed"],
        "latency_ms": result.latency_ms,
        "used_fallback": result.used_fallback,
        "pipeline_validation": result.validation,
        "score": score,
        "generated_wording": result.generated_wording,
        "response": result.summary,
    })

prior = {item["name"]: {"passed": item["passed"], "total": item["total"]}
         for item in baseline["candidates"]}
output = {
    "split": "v4_independent_valid",
    "system": "hybrid_evidence_first",
    "model": "mlx-community/Qwen2.5-1.5B-Instruct-4bit",
    "prior": prior,
    "passed": sum(item["passed"] for item in examples),
    "total": len(examples),
    "fallbacks": sum(item["used_fallback"] for item in examples),
    "latency_ms": {
        "total": sum(item["latency_ms"] for item in examples),
        "mean": statistics.mean(item["latency_ms"] for item in examples),
        "median": statistics.median(item["latency_ms"] for item in examples),
        "minimum": min(item["latency_ms"] for item in examples),
        "maximum": max(item["latency_ms"] for item in examples),
    },
    "examples": examples,
}
OUTPUT.write_text(json.dumps(output, indent=2) + "\n")
print(f"base_production_scaffold: {prior['base_production_scaffold']['passed']}/16")
print(f"adapter_v4: {prior['adapter_v4']['passed']}/16")
print(f"hybrid: {output['passed']}/16; fallbacks={output['fallbacks']}/16")
print(json.dumps(output["latency_ms"], indent=2))
