# Step 6: actual local learning loop

Step 6 connects explicit developer approval to controlled MLX-LM LoRA jobs:

`captured trace -> approved correction -> pending queue -> explicit job -> candidate -> server evaluation -> qualified route or rejection`

Cloud providers are not involved. Training starts only when
`POST /v1/training/jobs` includes `"execute": true`; the default remains a
non-training plan. Queue rows are snapshotted into the job and are marked used
only after training and adapter verification succeed.

## Frozen data

`scripts/build_v3_dataset.py` reproducibly creates the v3 corpus from the
team-authored Step 2/4 records plus 20 new team-authored examples. It does not
read `data/test.jsonl`.

| Split | Records | SHA-256 |
|---|---:|---|
| `data/v3/train.jsonl` | 56 | `03c3504c277c597a2eb434837edb7de73c80a82e3d0624d21621636164bf25d1` |
| `data/v3/valid.jsonl` | 6 | `f2a01afb455699c18066b8e5af1307f0ec1859ec7fa5ced50ec8af0cff64e018` |
| `data/v3/holdout.jsonl` | 6 | `6976effa2a99bc96effc3d9a9bba17fcf0776d123303f0f40753bdcfbc13abf6` |

All prompts are unique across splits. Every assistant response has the four
required headings and the evidence-only testing statement. Tokenization checks
found no 512-token truncation; supervised masks begin at `## Summary`. The new
holdout was frozen and was not evaluated because v3 failed validation. The
original three-example test split remains unchanged and unused.

## Executed job

Job 1 consumed one corrected-and-approved queue example and combined it with
the 56 curated training records. It trained rank-4 LoRA weights in four layers
from the frozen cached base model for 28 optimizer steps.

| Measurement | Actual result |
|---|---:|
| Training records | 57 |
| Validation records | 6 |
| Optimizer steps | 28 |
| Duration | 22.169 s |
| Peak MLX memory | 1.755 GB |
| Maximum resident set | 1,161,560,064 bytes |
| Trainable scalar parameters | 659,456 |
| Changed adapter tensors | 56 / 56 |
| Changed scalar parameters | 659,456 / 659,456 |
| Final validation loss | 1.383 |

Training losses at saved intervals were 3.036, 2.338, 2.224, 1.661, 1.749,
1.622, and 1.607. Validation losses at steps 1, 7, 14, 21, and 28 were 2.366,
2.128, 1.633, 1.486, and 1.383. The job log and adapter are in
`artifacts/training_jobs/1/training.log` and
`artifacts/adapters/adapter-v3/` respectively.

## Frozen validation gate

All variants used the same six inputs and deterministic inference settings.
The server owns the checks: exact four-section structure, repetition, exact
identifier retention, diff-content recall, contradictions, invented testing,
and unsupported statements.

| Variant | Passing examples |
|---|---:|
| Base, raw prompt | 0 / 6 |
| Base + production scaffold | 5 / 6 |
| Experimental v2 | 3 / 6 |
| v3 step 7 (selected) | 4 / 6 |
| v3 step 14 | 2 / 6 |
| v3 step 21 | 4 / 6 |
| v3 step 28 | 2 / 6 |

The frozen selection rule chose the earliest checkpoint among those with the
highest pass count, step 7. It still failed: one response invented a rename and
another invented `merge!`, emitted stray diff markers, and repeated content.
It also did not beat the scaffold baseline. Therefore `adapter-v3` is
`experimental_failed`, the `pr_summary` route remains `qwen-base`, and the
holdout was not opened. Lower validation loss did not override output quality.

Reproduce the corpus checks with:

```bash
source .venv/bin/activate
python scripts/build_v3_dataset.py --check
pytest
```
