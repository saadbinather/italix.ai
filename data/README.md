# Structured PR summary dataset

These examples are synthetic, team-authored fixtures created for ITALIX.ai. They
are not copied from cloud-model outputs or third-party repositories.

## Splits

- `train.jsonl`: 18 examples used for LoRA updates.
- `valid.jsonl`: 3 examples used for validation during training.
- `test.jsonl`: 3 untouched examples reserved for the Step 4 comparison.

Do not tune prompts, training settings, or checkpoints against `test.jsonl`.

## MLX-LM format

Each line is one JSON object with a `messages` array. The user message contains
a synthetic Git diff; the assistant message is the approved target. This is the
chat format accepted by MLX-LM LoRA tooling.

Every approved summary must use exactly these sections:

```text
## Summary
One concise statement of intent and outcome.
## Changes
- Concrete implementation detail(s).
## Testing
- Test or verification performed, or an explicit not-run reason.
## Risk
Low|Medium|High — concise rationale.
```

Quality gates are executable with `python scripts/validate_dataset.py`: valid
JSONL, two-message user/assistant conversations, expected roles, diff evidence,
all required headings in order, a valid risk level, no exact duplicate content,
no record shared between splits, and no pair with Jaccard token similarity at or
above 0.82. The expected total is 24 records with an 18/3/3 split.
