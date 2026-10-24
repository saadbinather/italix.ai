"""Generate one deterministic validation response with base and v1 adapter."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import time

import mlx.core as mx
from mlx_lm import generate, load


parser = argparse.ArgumentParser()
parser.add_argument("--model", required=True)
parser.add_argument("--adapter", required=True)
parser.add_argument("--validation", type=Path, default=Path("data/valid.jsonl"))
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--max-tokens", type=int, default=180)
args = parser.parse_args()

record = json.loads(args.validation.read_text(encoding="utf-8").splitlines()[0])
user_content = record["messages"][0]["content"]


def run(adapter_path: str | None) -> tuple[str, float, float]:
    model, tokenizer = load(args.model, adapter_path=adapter_path)
    prompt = tokenizer.apply_chat_template(
        [{"role": "user", "content": user_content}],
        tokenize=False,
        add_generation_prompt=True,
    )
    started = time.perf_counter()
    response = generate(
        model,
        tokenizer,
        prompt=prompt,
        max_tokens=args.max_tokens,
        verbose=False,
    ).strip()
    mx.synchronize()
    elapsed = time.perf_counter() - started
    peak_mib = mx.get_peak_memory() / 1024**2
    del model, tokenizer
    mx.clear_cache()
    return response, elapsed, peak_mib


base, base_seconds, base_peak = run(None)
adapted, adapted_seconds, adapted_peak = run(args.adapter)
result = {
    "source": "validation example 1",
    "generation_settings": {"max_tokens": args.max_tokens, "sampling": "default"},
    "prompt": user_content,
    "approved_target": record["messages"][1]["content"],
    "base": {"response": base, "seconds": base_seconds, "peak_mib": base_peak},
    "adapted": {
        "response": adapted,
        "seconds": adapted_seconds,
        "peak_mib": adapted_peak,
    },
}
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
print(json.dumps(result, indent=2))
