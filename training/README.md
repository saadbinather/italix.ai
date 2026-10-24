# Step 3: MLX-LM LoRA training

This step uses the existing local Qwen2.5 1.5B 4-bit model. The base model is
frozen; rank-8 LoRA adapters are inserted into the final eight transformer
layers. Training uses batch size 1, response-only loss, and a 512-token limit.

- `smoke.yaml`: three optimizer steps used to prove the training path.
- `v1.yaml`: 54 steps (three passes over 18 examples), with validation every
  nine steps and checkpoints every 18 steps.

MLX-LM's local dataset loader opens `test.jsonl` whenever it exists in the data
directory. Runs therefore point at the ignored `artifacts/step3_data` staging
directory, which contains only links to the training and validation files.

The full run overfit. Validation loss was best at step 18, so that checkpoint is
installed as `artifacts/adapters/v1/adapters.safetensors`; the step-54 result is
preserved as `final_step_54.safetensors`. The step-18 adapter reloads correctly,
but its qualitative validation generation repeats one heading and is worse than
the base response. Version 1 is a technical training artifact and must not be
treated as deployable.

Step 4 diagnosis, training attempts, fixed quality gates, and the rejected v2
result are recorded in `STEP4_REPORT.md`.

Logs, checkpoints, comparisons, and the machine-readable report live under the
ignored `artifacts/` directory. They remain local and are not committed.
