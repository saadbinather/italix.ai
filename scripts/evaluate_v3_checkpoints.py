"""Compare v3 checkpoints with frozen server-side validation gates."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from italix.evaluation import ServerEvaluator


parser = argparse.ArgumentParser()
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("candidate", nargs="+", help="NAME=adapter/directory")
args = parser.parse_args()

evaluator = ServerEvaluator()
rows = [json.loads(line) for line in Path("data/v3/valid.jsonl").read_text().splitlines()]
results = {
    "split": "valid",
    "policy": {
        "source": "italix.evaluation frozen constants",
        "selection": "highest pass count; earliest checkpoint breaks ties",
    },
    "candidates": [
        evaluator._candidate("base_raw", None, rows, scaffold=False),
        evaluator._candidate("base_scaffold", None, rows, scaffold=True),
        evaluator._candidate("adapter_v2", "artifacts/adapters/v2", rows, scaffold=True),
    ],
}
for spec in args.candidate:
    name, path = spec.split("=", 1)
    results["candidates"].append(evaluator._candidate(name, path, rows, scaffold=True))

scaffold = next(item for item in results["candidates"] if item["name"] == "base_scaffold")
v3 = [item for item in results["candidates"] if item["name"].startswith("v3_step_")]
best = max(v3, key=lambda item: (item["passed"], -int(item["name"].removeprefix("v3_step_"))))
results["selected"] = best["name"]
results["qualified"] = best["passed"] == best["total"] and best["passed"] > scaffold["passed"]
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(json.dumps(results, indent=2) + "\n")
for candidate in results["candidates"]:
    print(f"{candidate['name']}: {candidate['passed']}/{candidate['total']}")
print(f"selected: {results['selected']}; qualified={results['qualified']}")
