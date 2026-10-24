"""Load a small Qwen model on Metal and perform one measured generation."""

from __future__ import annotations

import resource
import time

import mlx.core as mx
from mlx_lm import generate, load

MODEL_ID = "mlx-community/Qwen2.5-1.5B-Instruct-4bit"
PROMPT = "In one sentence, explain why code reviews are useful."


def mib(value: int | float) -> float:
    return float(value) / 1024**2


print(f"Model: {MODEL_ID}")
print(f"Device: {mx.default_device()} (Metal available: {mx.metal.is_available()})")

load_started = time.perf_counter()
model, tokenizer = load(MODEL_ID)
load_seconds = time.perf_counter() - load_started

messages = [{"role": "user", "content": PROMPT}]
prompt = tokenizer.apply_chat_template(
    messages, tokenize=False, add_generation_prompt=True
)

generation_started = time.perf_counter()
response = generate(
    model,
    tokenizer,
    prompt=prompt,
    max_tokens=64,
    verbose=False,
)
mx.synchronize()
generation_seconds = time.perf_counter() - generation_started

# macOS reports ru_maxrss in bytes (Linux reports KiB).
process_peak_mib = mib(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
print(f"Prompt: {PROMPT}")
print(f"Response: {response.strip()}")
print(f"Model load time: {load_seconds:.2f} s")
print(f"Generation time: {generation_seconds:.2f} s")
print(f"Process peak RSS: {process_peak_mib:.1f} MiB")
print(f"MLX active Metal memory: {mib(mx.get_active_memory()):.1f} MiB")
print(f"MLX peak Metal memory: {mib(mx.get_peak_memory()):.1f} MiB")
