"""Save the deterministic pre-update LoRA tensors for change verification."""

from __future__ import annotations

import argparse
from pathlib import Path

import mlx.core as mx
from mlx.utils import tree_flatten
from mlx_lm import load
from mlx_lm.tuner.utils import linear_to_lora_layers


parser = argparse.ArgumentParser()
parser.add_argument("--model", required=True)
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--seed", type=int, default=42)
parser.add_argument("--num-layers", type=int, default=8)
parser.add_argument("--rank", type=int, default=8)
parser.add_argument("--scale", type=float, default=20.0)
args = parser.parse_args()

model, _ = load(args.model)
model.freeze()
mx.random.seed(args.seed)
linear_to_lora_layers(
    model,
    args.num_layers,
    {"rank": args.rank, "dropout": 0.0, "scale": args.scale},
)
weights = dict(tree_flatten(model.trainable_parameters()))
mx.eval(weights)
args.output.parent.mkdir(parents=True, exist_ok=True)
mx.save_safetensors(str(args.output), weights)
print(f"Saved {len(weights)} initial adapter tensors to {args.output}")
print(f"Trainable LoRA parameters: {sum(value.size for value in weights.values()):,}")
