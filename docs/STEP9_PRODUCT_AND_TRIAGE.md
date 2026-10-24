# Step 9: product journey and change-triage experiment

Step 9 keeps the historical PR-summary evidence intact and adds one narrower,
objectively scored workload: `change_triage`. Given a diff, it returns exactly:

```json
{"owner":"identity","risk":"high","reviewer":"security"}
```

The labels follow a fictional internal policy across payments, identity,
platform, growth, and product paths. This is useful repository routing behavior,
not customer data and not a task selected merely for easy formatting.

## Frozen data and gate

| Split | Records | SHA-256 |
|---|---:|---|
| Train | 60 | `e47eac46d58f28e1d0c5cd2536fb8ea692c10df12a844112aaf5c1bbf7cac42f` |
| Validation | 12 | `42c34d3b5ad79f4cd13410778d0d8105d9b93bf7d3a76b8f61780111a53a32c3` |
| Holdout | 12 | `0726e5652b9c52940717991d64dd8b388944ba0c6aa196d3030ead8d892d045e` |

The validation gate was frozen before training:

- 12/12 exact JSON outputs;
- quality at least equal to the full production-policy scaffold;
- compact specialist prompt uses no more than 40% of scaffold prompt tokens.

The holdout remains unopened because no candidate passed validation.

## Baselines

| Variant | Exact validation | Average prompt tokens |
|---|---:|---:|
| Base + compact specialist prompt | 0/12 | 140 |
| Base + full production policy and six examples | 6/12 | 391 |

## Bounded LoRA experiments

Only two fresh-base attempts were allowed.

| Candidate | Rank/layers | Selected step | Exact validation | Parameters changed | Duration | Peak MLX |
|---|---|---:|---:|---:|---:|---:|
| `triage-adapter-a` | 4 / 4 | 30 | 6/12 | 659,456 | 30.28 s | 1.381 GB |
| `triage-adapter-b` | 4 / 8 | 60 | 9/12 | 1,318,912 | 32.97 s | 1.515 GB |

Candidate B learned every owner and reviewer on validation but assigned the
wrong risk tier to two identity cases and one infrastructure case. It therefore
failed the exact gate even though it improved over both the compact baseline
and the long production scaffold. Validation loss alone did not qualify it.

Both candidates are `experimental_failed`. `qwen-base-triage` remains active,
activation returns HTTP 409 for either failed adapter, and the holdout was not
evaluated.

## Dashboard journey

The dashboard now leads with the product loop:

`Send -> Review -> Teach -> Train -> Prove -> Deploy`

Users can select `change_triage` in the live gateway, correct and approve an
answer, see the workload-specific queue, explicitly launch its frozen MLX-LM
recipe, inspect measured losses and parameter deltas, run the server-owned
evaluation, and activate only if the result becomes qualified. Registry and
rollback controls are workload-specific.

The cost page compares a hypothetical cloud-only scenario with a local-first
scenario using explicit cloud price, routing percentage, local per-request
compute, and fixed hosting/electricity inputs. It does not report realized
savings.

## Actual loop proof

A captured `auth/permissions/admin_guard.py` request was routed locally through
`qwen-base-triage`. The base response was incorrect, the developer correction
was approved as:

```json
{"owner":"identity","risk":"high","reviewer":"security"}
```

The example entered the `change_triage` queue. Attempting to activate
`triage-adapter-b` returned HTTP 409 because it is unqualified.
