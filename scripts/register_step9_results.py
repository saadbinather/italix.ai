"""Register measured Step 9 experiment evidence in the local SQLite registry."""

from __future__ import annotations

import json
from pathlib import Path
import re

import mlx.core as mx

from italix.database import Database, utc_now


ROOT = Path(__file__).resolve().parents[1]


def delta(initial_path: Path, trained_path: Path) -> dict:
    initial, trained = mx.load(str(initial_path)), mx.load(str(trained_path))
    changed_tensors = changed_elements = 0
    maximum = 0.0
    for name in initial:
        difference = mx.abs(trained[name] - initial[name])
        elements = int(mx.sum(difference != 0).item())
        changed_tensors += bool(elements)
        changed_elements += elements
        maximum = max(maximum, float(mx.max(difference).item()))
    return {"adapter_tensors": len(trained), "trainable_parameters": sum(x.size for x in trained.values()),
            "changed_tensors": changed_tensors, "changed_elements": changed_elements,
            "maximum_absolute_delta": maximum}


def metrics(version: str, checkpoint: int, validation_file: str) -> dict:
    folder = ROOT / f"artifacts/adapters/change-triage-{version}"
    log = (ROOT / f"artifacts/training/change-triage-{version}/training.log").read_text()
    evaluation = json.loads((ROOT / validation_file).read_text())
    selected = next(x for x in evaluation["candidates"] if x["name"] == f"step{checkpoint}")
    validation = [{"step": int(step), "loss": float(loss)}
                  for step, loss in re.findall(r"Iter (\d+): Val loss ([0-9.]+)", log)]
    return {
        "optimizer_steps": max(item["step"] for item in validation),
        "duration_seconds": float(re.search(r"\s+([0-9.]+) real", log).group(1)),
        "train_examples": 60, "validation_examples": 12, "queued_examples": 0,
        "training_losses": [float(x) for x in re.findall(r"Train loss ([0-9.]+)", log)],
        "validation_losses": validation,
        "peak_mlx_memory_gb": max(float(x) for x in re.findall(r"Peak mem ([0-9.]+) GB", log)),
        "selected_checkpoint": checkpoint, "validation_evaluation": selected,
        **delta(folder / "initial.safetensors", folder / f"checkpoint-{checkpoint}/adapters.safetensors"),
    }


def main() -> None:
    database = Database(ROOT / "var/italix.db")
    database.initialize()
    experiments = [
        ("triage-adapter-a", "v1", 30, "artifacts/evaluations/change_triage_checkpoints_validation.json"),
        ("triage-adapter-b", "v2", 60, "artifacts/evaluations/change_triage_v2_validation.json"),
    ]
    with database.connect() as connection:
        for candidate, version, checkpoint, evaluation_file in experiments:
            result = metrics(version, checkpoint, evaluation_file)
            adapter_path = f"artifacts/adapters/change-triage-{version}/checkpoint-{checkpoint}"
            if not connection.execute("SELECT 1 FROM training_jobs WHERE candidate_id=?", (candidate,)).fetchone():
                connection.execute(
                    """INSERT INTO training_jobs
                    (workload,example_count,status,created_at,candidate_id,adapter_path,log_path,
                     metrics_json,completed_at) VALUES (?,?, 'completed', ?,?,?,?,?,?)""",
                    ("change_triage", 60, utc_now(), candidate, adapter_path,
                     f"artifacts/training/change-triage-{version}/training.log", json.dumps(result), utc_now()),
                )
            evaluation = json.loads((ROOT / evaluation_file).read_text())
            chosen = next(x for x in evaluation["candidates"] if x["name"] == f"step{checkpoint}")
            registry_metrics = {**result, "evaluation": {"workload": "change_triage",
                "split": "valid", "candidates": [evaluation["candidates"][0], evaluation["candidates"][1],
                {**chosen, "name": "candidate"}], "qualified": False,
                "qualification_reason": "candidate did not pass all 12 exact validation cases"}}
            connection.execute(
                """INSERT INTO models (id,workload,kind,status,path,metrics_json,active,created_at)
                VALUES (?,?,'adapter','experimental_failed',?,?,0,?)
                ON CONFLICT(id) DO UPDATE SET status='experimental_failed',path=excluded.path,
                metrics_json=excluded.metrics_json,active=0""",
                (candidate, "change_triage", adapter_path, json.dumps(registry_metrics), utc_now()),
            )
    print("Registered two completed, experimental_failed change_triage experiments")


if __name__ == "__main__":
    main()
