# Phase 9 benchmark freeze and review

The Phase 8 dataset is frozen for this wiring comparison at SHA-256
`3fb9f141498f0a04d73509d9fd1832a7bb48c642b801d205c0b89e59342d5f22`.
This is an AI-assisted review of all 100 patch and label pairs. All 100 still
require independent human review. Full benchmark scoring remains blocked.

The policy expectations match the frozen routing rules and deterministic hybrid
baseline: 66 definitive labels (33 high, 22 medium, 11 low), 20 unknown paths,
10 conflicting policies and four truncated patches. The evidence regression
checks exact changed-line text. For the four truncated patches, the deleted
text is visible but the replacement is missing. They are abstention fixtures
and cannot establish a complete change summary.

| Review item | Cases | Suggested reviewer disposition |
| --- | --- | --- |
| Broken Ruby diff from delimiter splitting | 044, 084, 095 | Rebuild the patch from valid Ruby source and reassess the fact. Review the intended distinction between false and nil. |
| Wording supports a local predicate or configuration only | 001, 003, 006, 009, 010, 022, 023, 025, 027, 028, 029, 030, 032, 033, 035, 036, 039, 043, 047, 050, 054, 055, 060, 065, 068, 072, 076 and any composites using them | Require wording grounded in the snippet. Do not infer end-to-end enforcement, provider behavior, layout effects, caller contracts or actual safety from a line edit. |
| Stated intent partly depends on unseen implementation or types | 012, 017, 020, 031, 038, 042, 048, 049, 064, 075 | Require qualification or supporting code. For 042 use “adds a nonnegative bound”; for 075 distinguish PostgreSQL instant handling from preserving an original time zone. |
| Incomplete patch | 097–100 | Retain for input-validity and abstention checks. Exclude from complete semantic-change scoring. |
| Narrow scope and related patches | 001–080 and 081–096 | All complete hunks replace one line. The 16 multi-file cases combine changes from the 80 single-file cases. Of 112 complete hunk instances, 80 are unique and 28 are reused. Group by linked hunk before sampling or aggregating. Add independently reviewed multi-hunk changes before relying on a product-quality ranking. |

Other expected semantic facts are plausible descriptions of the changed lines,
subject to independent review. For 014 the edit shows an explicit transaction
wrapper and cannot establish whether the previous call already used an implicit
transaction. For 061 “subtracts the discount” is more precise than “includes
discounts.” Keep software risk unassessed until a reviewer has actual repository
context. Treat authentication policy risk and evidence of a security regression
as separate labels.

## Related-case map

Each composite or truncated case maps to its single-file source case.

- `081` → `001+011`, `082` → `012+022`, `083` → `023+033`, `084` → `034+044`
- `085` → `045+055`, `086` → `056+006`, `087` → `007+017`, `088` → `018+028`
- `089` → `029+039`, `090` → `040+050`, `091` → `003+004`, `092` → `013+014`
- `093` → `023+024`, `094` → `033+034`, `095` → `043+044`, `096` → `053+054`
- `097` → `009`, `098` → `019`, `099` → `029`, `100` → `039`

## Frozen smoke protocol

Run the three pinned models with native templates, the existing Phase 8 task
prompts, temperature zero, and a 160-token cap. Run the same three fixtures in
order: 001 (supported authorization predicate), 061 (out-of-policy business
logic), and 081 (conflicting multi-file policies). Collect the first model load
in a fresh process, then measure the warm calls. Exercise two switches in a
separate shared process, isolating unload and next load via the existing worker.
Use raw outputs for qualitative wiring observations only. Deterministic hybrid
triage supplies policy decisions throughout. Whole-process CPU RSS, MLX peak
allocation, and system-wide swap counters measure different quantities. Record
them separately. A full reviewed run will also need context-rich chat and
memory fixtures before recommending routes for those workloads.

From the repo root, after verifying the pinned snapshots:

```bash
mkdir -p artifacts/phase9
for model in qwen-base qwen3-4b qwen-coder-7b switch; do
  HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 .venv/bin/python \
    -m scripts.phase9_model_smoke "$model" "artifacts/phase9/$model.jsonl"
done
```

Use a new output path when repeating a measurement. Model load timings are
fresh-process timings and may benefit from the OS page cache. The first
request after each load may still incur MLX initialization overhead. The
switch timings include eviction and loading the next model.

## Run records

Local outputs are under `artifacts/phase9/`. The `*-eos.jsonl` files are the
matched rerun after fixing Coder's stop token. The pinned Coder conversion
declares model EOS ID 151643 and native chat EOS ID 151645. MLX-LM originally
used only the model config ID, so Coder emitted a literal chat terminator.
The loader now preserves both IDs. The original smoke files remain available
for diagnosis.

`snapshot-metadata.json` records Hub file hashes and sizes.
`integrity.json` records verification of all files in both new snapshots and
of the originally cached nine-file 1.5B payload. Verification used SHA-256
for LFS weights and Git blob hashes for repository files. The snapshot config
and tokenizer files also match the pinned metadata. The full comparison
runner remains gated on independent review.
