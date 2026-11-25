"""Run the frozen Phase 9 offline smoke protocol or isolated switching check."""
import argparse
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import resource
import subprocess
from time import perf_counter

from italix.engines import LOCAL_MODELS, LocalMLXEngine, _MLX_WORKER
from italix.hybrid_triage import hybrid_triage, patch_evidence
from scripts.compare_local_models import PILOT, TASKS, MAX_TOKENS


MODEL_IDS = tuple(LOCAL_MODELS)
CASE_IDS = ("pilot-001", "pilot-061", "pilot-081")
PILOT_DIGEST = "3fb9f141498f0a04d73509d9fd1832a7bb48c642b801d205c0b89e59342d5f22"


def machine_memory():
    vm = subprocess.check_output(["vm_stat"], text=True).splitlines()
    swap = subprocess.check_output(["sysctl", "-n", "vm.swapusage"], text=True).strip()
    rss = subprocess.check_output(["ps", "-o", "rss=", "-p", str(os.getpid())], text=True)
    return {
        "swap": swap,
        "swap_counters": {line.split(":")[0]: int(line.split(":")[1].strip().rstrip("."))
                          for line in vm if line.startswith(("Swapins:", "Swapouts:"))},
        "rss_kib": int(rss.strip()),
        "peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
    }


def load_model(engine):
    started = perf_counter()
    _MLX_WORKER.submit(engine._load, None).result()
    return (perf_counter() - started) * 1000


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model", choices=(*MODEL_IDS, "switch"))
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    raw = PILOT.read_bytes()
    if hashlib.sha256(raw).hexdigest() != PILOT_DIGEST:
        parser.error("pilot no longer matches the Phase 9 freeze")
    rows = {row["id"]: row for row in map(json.loads, raw.splitlines())}

    with args.output.open("x") as stream:
        def write(row):
            print(json.dumps(row), file=stream, flush=True)

        write({"pilot_sha256": PILOT_DIGEST, "smoke_only": True, "cases": CASE_IDS,
               "max_tokens": MAX_TOKENS, "temperature": 0, "prompts": TASKS,
               "mlx": version("mlx"), "mlx_lm": version("mlx-lm"), "before": machine_memory()})
        for model_id in MODEL_IDS if args.model == "switch" else (args.model,):
            engine = LocalMLXEngine(model_id=model_id)
            try:
                write({"model": model_id, "revision": LOCAL_MODELS[model_id].revision,
                       "load_ms": load_model(engine), **machine_memory()})
                for case_id in CASE_IDS[:1] if args.model == "switch" else CASE_IDS:
                    diff = rows[case_id]["diff"]
                    _, excerpts = patch_evidence(diff)
                    baseline = hybrid_triage(diff, explain=False, engine=engine)
                    write({"id": case_id, "baseline_result": baseline["result"],
                           "abstention_reason": baseline["abstention_reason"]})
                    tasks = ("summary",) if args.model == "switch" else TASKS
                    for task in tasks:
                        content = json.dumps(excerpts) if task == "evidence" else diff
                        started = perf_counter()
                        generation = engine.generate(
                            [{"role": "system", "content": TASKS[task]},
                             {"role": "user", "content": content}],
                            max_tokens=MAX_TOKENS, temperature=0,
                        )
                        write({"model": model_id, "id": case_id, "task": task,
                               "prediction": generation.text, "latency_ms": (perf_counter() - started) * 1000,
                               "prompt_tokens": generation.prompt_tokens,
                               "completion_tokens": generation.completion_tokens,
                               **(generation.metadata or {}), **machine_memory()})
            except Exception as exc:
                write({"model": model_id, "runtime_error": str(exc)})
                engine.unload()
                raise
        started = perf_counter()
        engine.unload()
        write({"unload_ms": (perf_counter() - started) * 1000, "after": machine_memory()})


if __name__ == "__main__":
    main()
