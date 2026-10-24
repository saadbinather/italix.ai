"""Compare v4 against two frozen-base prompts on independent validation only."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import italix.evaluation as evaluation
from italix.evaluation import ServerEvaluator


COMPACT_PROMPT = """Summarize only facts in the Git diff. Preserve exact identifiers and fallback values.
Return ## Summary, ## Changes, ## Testing, and ## Risk exactly once in that order.
Use '- Not run (not shown in diff).' unless tests appear in the diff. Begin risk with Low, Medium, or High and an em dash."""


parser = argparse.ArgumentParser()
parser.add_argument("--adapter", default="artifacts/adapters/adapter-v4")
parser.add_argument("--output", type=Path, default=Path("artifacts/evaluations/v4_independent_validation.json"))
args = parser.parse_args()

root = Path(__file__).resolve().parents[1]
rows = [json.loads(line) for line in (root / "data/v4/independent_valid.jsonl").read_text().splitlines()]
evaluator = ServerEvaluator(root)

# All candidates use ServerEvaluator._candidate, which freezes decoding and scoring.
production = evaluator._candidate("base_production_scaffold", None, rows, scaffold=True)
original_prompt = evaluation.SYSTEM_PROMPT
try:
    evaluation.SYSTEM_PROMPT = COMPACT_PROMPT
    compact = evaluator._candidate("base_compact_prompt", None, rows, scaffold=True)
finally:
    evaluation.SYSTEM_PROMPT = original_prompt
candidate = evaluator._candidate("adapter_v4", str(root / args.adapter), rows, scaffold=True)

qualified = candidate["passed"] == candidate["total"] and candidate["passed"] > production["passed"]
result = {
    "split": "v4_independent_valid",
    "rubric": json.loads((root / "data/v4/evaluation_rubric.json").read_text()),
    "candidates": [production, compact, candidate],
    "qualified": qualified,
    "qualification_reason": "candidate passed every case and exceeded production scaffold" if qualified else "candidate failed a case or did not exceed production scaffold",
}
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(json.dumps(result, indent=2) + "\n")
for item in result["candidates"]:
    print(f"{item['name']}: {item['passed']}/{item['total']}")
print(f"qualified={qualified}")
