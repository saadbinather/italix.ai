# Phase 8 local-model comparison

## Pilot and independent review

`data/phase8/pilot-v1.jsonl` contains 100 original synthetic patch drafts. Their scope includes access checks, database queries and migrations, retries, caching, infrastructure, billing, and UI behavior. There are 16 multi-file cases. The 34 human-review cases cover unknown paths, conflicting policies, and truncated hunks. The corpus includes intentionally narrow patches and related single-file and multi-file cases. Keep related cases together and report results by case type to avoid over-weighting those families.

Each row records the patch, provenance, independently written policy expectation, semantic facts and cited before/after lines, and a separate software-risk field. Automated tests check all policy expectations against hybrid v2 and check that expected evidence is present. Independent human review is pending and actual software risk is unassessed. The pilot has no upstream source code. The SHA-256 in `data/phase8/SHA256SUMS` identifies the exact JSONL.

Before formal scoring, have a reviewer other than the author check each case from the raw patch and policy before looking at the proposed labels. Record reviewer identity or stable pseudonym, reviewed patch digest, disposition, and independently derived labels. A second reviewer adjudicates disagreements and records rationale. Check summaries against changed lines and available context. Record insufficient evidence when the patch alone cannot establish runtime impact. Evaluate real software risk separately with relevant context, tests, and evidence of impact. The path policy risk label is a property of the repository's routing rule.

For richer fixtures, the [GitHub PR files API](https://docs.github.com/en/rest/pulls/pulls#list-pull-requests-files) can retrieve selected changes from pinned permissively licensed repositories. Candidate repositories include [CPython](https://github.com/python/cpython/blob/main/LICENSE), [Go](https://github.com/golang/go/blob/master/LICENSE), and [Kubernetes](https://github.com/kubernetes/kubernetes/blob/master/LICENSE). For each selected file, verify license coverage at the exact commit, keep required notices, and record repository, commit pair, PR, file, license and patch digest. Review contributed PR text and hosted dataset redistribution terms separately. The [CodeReviewer paper](https://www.microsoft.com/en-us/research/publication/automating-code-review-activities-by-large-scale-pre-training/) provides a sampling reference. Use repository-disjoint splits, group cherry-picks and related revisions, and check normalized hunk similarity against training, development, and other accessible evaluation data before inclusion. Keep the reserved final test unopened.

## Model catalog and download approval

| Catalog ID | Pinned snapshot | Full snapshot bytes | Context | Estimated MLX working set at 4K |
| --- | --- | ---: | ---: | ---: |
| `qwen-base` | [Qwen2.5-1.5B-Instruct, 4-bit](https://huggingface.co/mlx-community/Qwen2.5-1.5B-Instruct-4bit/tree/8b403126fc14f14cfc99bb4cfa72ecbc129ea677) | 880,172,064 | 32,768 | 1.5–3 GiB |
| `qwen3-4b` | [Qwen3-4B-Instruct-2507, 4-bit](https://huggingface.co/mlx-community/Qwen3-4B-Instruct-2507-4bit/tree/50d427756c6b1b2fe0c0a10f67fbda1fc8e82c1b) | 2,278,972,236 | 262,144 | 3–5 GiB |
| `qwen-coder-7b` | [Qwen2.5-Coder-7B-Instruct, 4-bit](https://huggingface.co/mlx-community/Qwen2.5-Coder-7B-Instruct-4bit/tree/019cc73c45c770444708a6dd8690c66243cc5c80) | 4,295,890,004 | 32,768 | 5–8 GiB |

Snapshot totals include documentation and repository metadata. The two new snapshots total 6,574,862,240 bytes (6.12 GiB) before filesystem or cache overhead. All three list Apache-2.0. At batch size one and 4K tokens, the unquantized 16-bit key/value cache estimates are 112, 576 and 224 MiB, respectively. Working-set ranges include estimated runtime buffers, are planning figures, and exclude macOS and other applications. Use short prompts on a 16 GB Mac even when the model metadata advertises a longer context. The Qwen3 model is a general instruction-following candidate. The Coder model is a code-specialized candidate. Treat any advantage on this pilot as a hypothesis until measured.

Each candidate requires separate download approval. Once approved and manually cached, use its pinned catalog ID as `ITALIX_HYBRID_MODEL` to enable it for optional hybrid explanations. The backend accepts only the known model IDs. MLX reads the selected model's local tokenization and chat template. The MLX worker holds one resident model and switches only when a request needs a different one. Existing chat routing and adapters retain their base model.

## Reproducible zero-shot protocol

Run each model in a separate offline process, on the same machine and MLX versions. Run the smoke mode as a wiring check. The full command requires independent review status on every row and a matching checksum.

```bash
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 .venv/bin/python -m scripts.compare_local_models qwen-base results-base.jsonl
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 .venv/bin/python -m scripts.compare_local_models qwen3-4b results-qwen3.jsonl
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 .venv/bin/python -m scripts.compare_local_models qwen-coder-7b results-coder.jsonl
```

Use identical task instructions and raw inputs, greedy decoding and a 160-token generation cap. Keep native chat templates and record token counts. Run the deterministic hybrid route as the policy baseline. Score policy exact match, valid abstentions, invalid JSON and incorrect accepted decisions separately. For summaries, blind reviewers to the candidate and score supported claims, unsupported or contradictory claims, and missed required facts. For evidence selection, score precision and recall against independently reviewed changed-line IDs. Record model revision, pilot digest, MLX versions, prompt and generation tokens, latency, decode throughput and process peak MLX memory. Report cold load separately from warm inference and summarize warm median and p95. A smoke result does not establish comparative performance or qualification.

Review and expand the pilot before ranking models. Use the ranking to select a local explanation model for a second controlled Gateway run, comparing grounded evidence and latency with the policy-only hybrid baseline. Preserve the existing qualification and activation workflow.
