"""Explicit, synchronous MLX-LM training-job execution for the MVP."""

from __future__ import annotations

import json
from hashlib import sha256
import os
from pathlib import Path
import re
import subprocess
import sys
import time

import yaml

from italix.database import Database, TRAINING_DATA
from italix.privacy import contains_secret, redact
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
            return {"data": TRAINING_DATA[workload], "prompt": COMPACT_PROMPT,
                    "layers": 8, "iters": 80, "learning_rate": 0.00002,
                    "seed": 117, "max_seq_length": 384, "eval_every": 20,
                    "estimated_duration_seconds": "30-90",
                    "estimated_peak_mlx_memory_gb": 2.0,
                    "estimated_trainable_parameters": 1_318_912}
        if workload == "pr_summary":
            return {"data": TRAINING_DATA[workload], "prompt": SYSTEM_PROMPT,
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
        job = self.database.training_job(job_id)
        if not job or not job["dataset_checksums_json"]:
            raise ValueError("job has no dataset snapshot; create a new plan")
        checksums = json.loads(job["dataset_checksums_json"])
        curated = {}
        for name in ("train.jsonl", "valid.jsonl"):
            content = (self.root / spec["data"] / name).read_bytes()
            if sha256(content).hexdigest() != checksums[name]:
                raise ValueError("curated dataset changed; create a new plan")
            curated[name] = [json.loads(line) for line in content.splitlines()]
        queued = []
        examples = self.database.job_examples(job_id)
        if len(examples) != job["example_count"]:
            raise ValueError("training snapshot is incomplete; create a new plan")
        expected_status = "running" if job["status"] == "running" else "pending"
        for example in examples:
            if example["status"] != expected_status:
                raise ValueError("training example is no longer pending; create a new plan")
            if not example["unchanged"]:
                raise ValueError("reviewed example changed; create a new plan")
            messages = json.loads(example["messages_json"])
            if not any(message["role"] == "system" for message in messages):
                messages.insert(0, {"role": "system", "content": spec["prompt"]})
            messages.append({"role": "assistant", "content": example["approved_response"]})
            queued.append({"messages": messages})
        train = curated["train.jsonl"] + queued
        validation = curated["valid.jsonl"]
        if any(contains_secret(m["content"]) for row in train + validation for m in row["messages"]):
            raise ValueError("training export blocked because a row resembles a credential")

        def prompt_key(row):
            return tuple((m["role"], m["content"]) for m in row["messages"] if m["role"] != "system")[:-1]

        train_prompts = {prompt_key(row) for row in train}
        if len(train_prompts) != len(train):
            raise ValueError("duplicate prompts in the reviewed training export")
        if train_prompts & {prompt_key(row) for row in validation}:
            raise ValueError("exact prompt overlap between training and validation")
        if (destination / "test.jsonl").exists():
            raise RuntimeError("training staging directory unexpectedly contains test.jsonl")
        destination.mkdir(mode=0o700, parents=True, exist_ok=True)
        for name, rows in (("train", train), ("valid", validation)):
            (destination / f"{name}.jsonl").write_text(
                "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n"
            )
        return len(train), len(validation)

    @staticmethod
    def _parameter_delta(initial_path: Path, trained_path: Path) -> dict:
        import mlx.core as mx

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

    def execute(self, job_id: int, candidate_id: str, *, training_objective: dict | None = None) -> dict:
        job = self.database.training_job(job_id)
        if not job or job["status"] != "planned":
            raise ValueError("training job must exist and be planned")
        if training_objective is not None and job["workload"] != "change_triage":
            raise ValueError("The optional risk objective is only available for change triage")
        spec = self._spec(job["workload"])
        work = self.root / f"artifacts/training_jobs/{job_id}"
        data_path = work / "data"
        adapter_path = self.root / f"artifacts/adapters/{candidate_id}"
        log_path = work / "training.log"
        self.database.start_training_job(job_id, candidate_id)
        started = time.perf_counter()
        try:
            work.mkdir(mode=0o700, parents=True, exist_ok=True)
            adapter_path.mkdir(mode=0o700, parents=True, exist_ok=False)
            train_count, valid_count = self._export_data(job_id, data_path, spec)
            dataset_hashes = {
                name: sha256((data_path / name).read_bytes()).hexdigest()
                for name in ("train.jsonl", "valid.jsonl")
            }
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
            if training_objective is not None:
                config["training_objective"] = training_objective
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
            launcher = (
                [str(Path(__file__).with_name("weighted_lora.py"))]
                if training_objective is not None else ["-m", "mlx_lm", "lora"]
            )
            command = [
                "/usr/bin/time",
                "-l",
                sys.executable,
                *launcher,
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
            if any(sha256((data_path / name).read_bytes()).hexdigest() != digest
                   for name, digest in dataset_hashes.items()):
                raise ValueError("exported dataset changed during training")
            log = redact(initial.stdout + trained.stdout)
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
                "model_revision": model_path.name,
                "training_configuration": config,
                "curated_dataset_sha256": json.loads(job["dataset_checksums_json"]),
                "exported_dataset_sha256": dataset_hashes,
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
            self.database.fail_training_job(job_id, f"{type(exc).__name__}: {redact(str(exc))}")
            raise
