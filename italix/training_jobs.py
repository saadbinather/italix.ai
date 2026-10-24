"""Explicit, synchronous MLX-LM training-job execution for the MVP."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

import mlx.core as mx
import yaml

from italix.database import Database
from italix.engines import cached_qwen_path
from italix.pr_summary import SYSTEM_PROMPT
from italix.change_triage import COMPACT_PROMPT


class TrainingJobRunner:
    def __init__(self, database: Database, root: str | Path | None = None):
        self.database = database
        self.root = Path(root or Path(__file__).resolve().parents[1])

    @staticmethod
    def _spec(workload: str) -> dict:
        if workload == "change_triage":
            return {"data": "data/change_triage", "prompt": COMPACT_PROMPT,
                    "layers": 8, "iters": 80, "learning_rate": 0.00002,
                    "seed": 117, "max_seq_length": 384, "eval_every": 20,
                    "estimated_duration_seconds": "30-90",
                    "estimated_peak_mlx_memory_gb": 2.0,
                    "estimated_trainable_parameters": 1_318_912}
        if workload == "pr_summary":
            return {"data": "data/v3", "prompt": SYSTEM_PROMPT,
                    "layers": 4, "iters": 28, "learning_rate": 0.00002,
                    "seed": 43, "max_seq_length": 512, "eval_every": 7,
                    "estimated_duration_seconds": "20-60",
                    "estimated_peak_mlx_memory_gb": 2.0,
                    "estimated_trainable_parameters": 659_456}
        raise ValueError(f"unsupported training workload: {workload}")

    @classmethod
    def public_config(cls, workload: str = "pr_summary") -> dict:
        spec = cls._spec(workload)
        return {
            "engine": "MLX-LM",
            "base_model": "mlx-community/Qwen2.5-1.5B-Instruct-4bit",
            "fine_tune_type": "LoRA",
            "rank": 4,
            "workload": workload,
            "trainable_layers": spec["layers"],
            "optimizer_steps": spec["iters"],
            "learning_rate": spec["learning_rate"],
            "batch_size": 1,
            "max_sequence_length": spec["max_seq_length"],
            "mask_prompt": True,
            "execution": "synchronous local optimization",
            "cloud_required": False,
            "estimated_resources": {
                "duration_seconds": spec["estimated_duration_seconds"],
                "peak_mlx_memory_gb": spec["estimated_peak_mlx_memory_gb"],
                "trainable_parameters": spec["estimated_trainable_parameters"],
            },
        }

    def _run(self, command: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            command,
            cwd=self.root,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=True,
            env={**os.environ, "TOKENIZERS_PARALLELISM": "true"},
        )

    def _export_data(self, job_id: int, destination: Path, spec: dict) -> tuple[int, int]:
        destination.mkdir(parents=True, exist_ok=True)
        curated_train = [
            json.loads(line)
            for line in (self.root / spec["data"] / "train.jsonl").read_text().splitlines()
        ]
        validation = [
            json.loads(line)
            for line in (self.root / spec["data"] / "valid.jsonl").read_text().splitlines()
        ]
        queued = []
        for example in self.database.job_examples(job_id):
            messages = json.loads(example["messages_json"])
            if not any(message["role"] == "system" for message in messages):
                messages.insert(0, {"role": "system", "content": spec["prompt"]})
            messages.append({"role": "assistant", "content": example["approved_response"]})
            queued.append({"messages": messages})
        train = curated_train + queued
        for name, rows in (("train", train), ("valid", validation)):
            (destination / f"{name}.jsonl").write_text(
                "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n"
            )
        if (destination / "test.jsonl").exists():
            raise RuntimeError("training staging directory unexpectedly contains test.jsonl")
        return len(train), len(validation)

    @staticmethod
    def _parameter_delta(initial_path: Path, trained_path: Path) -> dict:
        initial = mx.load(str(initial_path))
        trained = mx.load(str(trained_path))
        if set(initial) != set(trained):
            raise RuntimeError("initial and trained adapter tensors differ")
        changed_tensors = 0
        changed_elements = 0
        maximum_delta = 0.0
        for name in initial:
            delta = mx.abs(trained[name] - initial[name])
            elements = int(mx.sum(delta != 0).item())
            if elements:
                changed_tensors += 1
                changed_elements += elements
                maximum_delta = max(maximum_delta, float(mx.max(delta).item()))
        if changed_elements == 0:
            raise RuntimeError("optimizer completed without changing adapter parameters")
        return {
            "adapter_tensors": len(initial),
            "trainable_parameters": sum(value.size for value in trained.values()),
            "changed_tensors": changed_tensors,
            "changed_elements": changed_elements,
            "maximum_absolute_delta": maximum_delta,
        }

    def execute(self, job_id: int, candidate_id: str) -> dict:
        job = self.database.training_job(job_id)
        if not job or job["status"] != "planned":
            raise ValueError("training job must exist and be planned")
        spec = self._spec(job["workload"])
        work = self.root / f"artifacts/training_jobs/{job_id}"
        data_path = work / "data"
        adapter_path = self.root / f"artifacts/adapters/{candidate_id}"
        log_path = work / "training.log"
        work.mkdir(parents=True, exist_ok=True)
        adapter_path.mkdir(parents=True, exist_ok=True)
        self.database.start_training_job(job_id)
        started = time.perf_counter()
        try:
            train_count, valid_count = self._export_data(job_id, data_path, spec)
            config = {
                "train": True,
                "fine_tune_type": "lora",
                "seed": spec["seed"],
                "num_layers": spec["layers"],
                "batch_size": 1,
                "iters": spec["iters"],
                "val_batches": -1,
                "learning_rate": spec["learning_rate"],
                "steps_per_report": 4,
                "steps_per_eval": spec["eval_every"],
                "save_every": spec["eval_every"],
                "max_seq_length": spec["max_seq_length"],
                "mask_prompt": True,
                "adapter_path": str(adapter_path.relative_to(self.root)),
                "lora_parameters": {"rank": 4, "dropout": 0.0, "scale": 8.0},
            }
            config_path = work / "config.yaml"
            config_path.write_text(yaml.safe_dump(config, sort_keys=False))
            model_path = cached_qwen_path()
            initial_path = adapter_path / "initial.safetensors"
            initial = self._run(
                [
                    sys.executable,
                    "scripts/save_initial_adapter.py",
                    "--model",
                    str(model_path),
                    "--output",
                    str(initial_path),
                    "--num-layers",
                    str(spec["layers"]),
                    "--rank",
                    "4",
                    "--scale",
                    "8",
                    "--seed",
                    str(spec["seed"]),
                ]
            )
            command = [
                "/usr/bin/time",
                "-l",
                sys.executable,
                "-m",
                "mlx_lm",
                "lora",
                "--model",
                str(model_path),
                "--data",
                str(data_path.relative_to(self.root)),
                "--adapter-path",
                str(adapter_path.relative_to(self.root)),
                "-c",
                str(config_path.relative_to(self.root)),
            ]
            trained = self._run(command)
            log = initial.stdout + trained.stdout
            log_path.write_text(log)
            duration = time.perf_counter() - started
            delta = self._parameter_delta(initial_path, adapter_path / "adapters.safetensors")
            train_losses = [float(value) for value in re.findall(r"Train loss ([0-9.]+)", log)]
            validation = [
                {"step": int(step), "loss": float(loss)}
                for step, loss in re.findall(r"Iter (\d+): Val loss ([0-9.]+)", log)
            ]
            peak_memory = [float(value) for value in re.findall(r"Peak mem ([0-9.]+) GB", log)]
            rss = re.search(r"(\d+)\s+maximum resident set size", log)
            metrics = {
                "optimizer_steps": spec["iters"],
                "duration_seconds": duration,
                "train_examples": train_count,
                "validation_examples": valid_count,
                "queued_examples": len(self.database.job_examples(job_id)),
                "training_losses": train_losses,
                "validation_losses": validation,
                "peak_mlx_memory_gb": max(peak_memory) if peak_memory else None,
                "maximum_resident_set_bytes": int(rss.group(1)) if rss else None,
                **delta,
            }
            return self.database.finish_training_job(
                job_id,
                candidate_id=candidate_id,
                adapter_path=str(adapter_path.relative_to(self.root)),
                log_path=str(log_path.relative_to(self.root)),
                metrics=metrics,
            )
        except Exception as exc:
            self.database.fail_training_job(job_id, f"{type(exc).__name__}: {exc}")
            raise
