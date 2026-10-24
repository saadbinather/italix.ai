"""Prove that optimizer steps changed the saved adapter tensors."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

import mlx.core as mx


parser = argparse.ArgumentParser()
parser.add_argument("initial", type=Path)
parser.add_argument("trained", type=Path)
args = parser.parse_args()

initial = mx.load(str(args.initial))
trained = mx.load(str(args.trained))
if set(initial) != set(trained):
    raise SystemExit("Adapter tensor names differ between initial and trained files")

changed = 0
changed_elements = 0
max_delta = 0.0
for name in sorted(initial):
    if initial[name].shape != trained[name].shape:
        raise SystemExit(f"Shape changed for {name}")
    delta = mx.abs(trained[name] - initial[name])
    tensor_max = float(mx.max(delta).item())
    elements = int(mx.sum(delta != 0).item())
    if elements:
        changed += 1
        changed_elements += elements
        max_delta = max(max_delta, tensor_max)

def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

print(f"Adapter tensors: {len(initial)}")
print(f"Changed tensors: {changed}")
print(f"Changed scalar elements: {changed_elements:,}")
print(f"Maximum absolute delta: {max_delta:.8f}")
print(f"Initial SHA-256: {digest(args.initial)}")
print(f"Trained SHA-256: {digest(args.trained)}")
if changed == 0 or changed_elements == 0:
    raise SystemExit("FAIL: no adapter parameter changed")
print("PASS: optimizer updates changed real adapter parameters")
