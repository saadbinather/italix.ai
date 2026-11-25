"""Collect zero-shot predictions for the Phase 8 pilot, one offline model per process."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
from time import perf_counter

from italix.change_triage import PRODUCTION_PROMPT
from italix.engines import LOCAL_MODELS, LocalMLXEngine
from italix.hybrid_triage import patch_evidence, ReviewRequired


PILOT = Path(__file__).resolve().parents[1] / "data/phase8/pilot-v1.jsonl"
TASKS = {
    "summary": "Write a factual one-sentence PR summary. Cite only facts supported by the patch.",
    "evidence": 'Select up to three IDs supporting the main semantic changes. Return only {"evidence_ids":[1]}.',
    "policy": PRODUCTION_PROMPT.split("Use the first matching path")[0]
    .replace("Return only one compact JSON object\nwith string keys owner, risk, reviewer in that order.",
             'Return {"owner":"…","risk":"…","reviewer":"…"} or {"abstain":true}.')
    + "\nConsider every changed file. Abstain on malformed patches, unknown paths, or conflicting policies.",
}
MAX_TOKENS = 160


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model", choices=LOCAL_MODELS)
    parser.add_argument("output", type=Path)
    parser.add_argument("--smoke", action="store_true", help="Run one unreviewed case as a wiring check")
    args = parser.parse_args()
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    pilot_bytes = PILOT.read_bytes()
    digest = hashlib.sha256(pilot_bytes).hexdigest()
    if digest != PILOT.with_name("SHA256SUMS").read_text().split()[0]:
        parser.error("pilot checksum mismatch")
    rows = [json.loads(line) for line in pilot_bytes.splitlines()]
    if args.smoke:
        rows = rows[:1]
    elif any(row["review_status"] != "independently_reviewed" for row in rows):
        parser.error("complete independent review before running the comparison")
    from importlib.metadata import version

    spec = LOCAL_MODELS[args.model]
    spec.cached_path()
    engine = LocalMLXEngine(model_id=args.model)
    with args.output.open("x") as stream:
        def write(row):
            print(json.dumps(row), file=stream, flush=True)

        write({"dataset_sha256": digest, "model": spec.repository, "revision": spec.revision,
               "temperature": 0, "max_tokens": MAX_TOKENS, "hardware": platform.platform(),
               "machine": platform.machine(), "mlx_lm": version("mlx-lm"), "mlx": version("mlx"),
               "task_prompts": TASKS, "smoke": args.smoke})
        try:
            for row in rows:
                diff = row["diff"]
                try:
                    _, excerpts = patch_evidence(diff)
                except ReviewRequired:
                    excerpts = []
                for task, prompt in TASKS.items():
                    content = json.dumps(excerpts) if task == "evidence" else diff
                    started = perf_counter()
                    generation = engine.generate(
                        [{"role": "system", "content": prompt}, {"role": "user", "content": content}],
                        max_tokens=MAX_TOKENS, temperature=0,
                    )
                    write({"id": row["id"], "task": task, "prediction": generation.text,
                           "latency_ms": (perf_counter() - started) * 1000,
                           "prompt_tokens": generation.prompt_tokens,
                           "completion_tokens": generation.completion_tokens, **(generation.metadata or {})})
        finally:
            engine.unload()


if __name__ == "__main__":
    main()
