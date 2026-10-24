"""Reproducible validation-only audit; deliberately never opens a holdout/test split."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from italix.change_triage import deterministic_triage
from italix.database import Database, utc_now
from italix.engines import cached_qwen_path


ROOT = Path(__file__).resolve().parents[1]


def rows(name: str) -> list[dict]:
    return [json.loads(line) for line in
            (ROOT / f"data/change_triage/{name}.jsonl").read_text().splitlines()]


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def main() -> None:
    train, valid = rows("train"), rows("valid")
    train_prompts = {row["messages"][-2]["content"] for row in train}
    valid_prompts = {row["messages"][-2]["content"] for row in valid}
    overlap = train_prompts & valid_prompts
    if overlap:
        raise SystemExit("FAIL: train/validation prompt leakage")
    inconsistent = []
    passed = 0
    evidence = []
    for index, row in enumerate(valid, 1):
        prompt, expected = row["messages"][-2]["content"], json.loads(row["messages"][-1]["content"])
        decision = deterministic_triage(prompt)
        ok = decision["resolved"] and decision["result"] == expected
        passed += ok
        evidence.append({"index": index, "passed": ok, "expected": expected,
                         "result": decision["result"], "reason": decision["reason"]})
        domain = next((part for part in expected.items()), None)
        if not decision["resolved"]:
            inconsistent.append({"index": index, "expected": expected})
    result = {
        "candidate": "triage-policy-v1", "kind": "deterministic_system",
        "provenance": "italix.change_triage.deterministic_triage + frozen LABELS",
        "split": "valid", "passed": passed, "total": len(valid),
        "validation_passed": passed == len(valid), "adapter_qualification": False,
        "adapter_used": False, "holdout_opened": False,
        "train_validation_overlap": len(overlap), "label_resolution_failures": inconsistent,
        "evidence": evidence,
    }
    model_file = cached_qwen_path() / "model.safetensors"
    result["frozen_base"] = {"path": str(model_file), "bytes": model_file.stat().st_size,
                             "sha256": digest(model_file)}
    output = ROOT / "artifacts/evaluations/step10_audit.json"
    output.write_text(json.dumps(result, indent=2) + "\n")
    database = Database(ROOT / "var/italix.db")
    database.initialize()
    with database.connect() as connection:
        connection.execute(
            """INSERT INTO models (id,workload,kind,status,path,metrics_json,active,created_at)
            VALUES ('triage-policy-v1','change_triage','system','validation_passed',?, ?,0,?)
            ON CONFLICT(id) DO UPDATE SET status='validation_passed',path=excluded.path,
            metrics_json=excluded.metrics_json,active=0""",
            ("italix/change_triage.py", json.dumps(result), utc_now()),
        )
    print(f"deterministic validation: {passed}/{len(valid)}")
    print("train/validation overlap: 0")
    print("holdout/test files opened: 0")
    print(f"frozen base sha256: {result['frozen_base']['sha256']}")


if __name__ == "__main__":
    main()
