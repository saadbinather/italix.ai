"""Create and freeze the independently authored v4 PR-summary validation set.

This script deliberately reads only the v4 training corpus. It never opens any
historical validation or sealed holdout split.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from italix.evaluation import score_response
from italix.pr_summary import SYSTEM_PROMPT


ROOT = Path(__file__).resolve().parents[1]
TRAIN = ROOT / "data/v4/train.jsonl"
OUT = ROOT / "data/v4/independent_valid.jsonl"
MANIFEST = ROOT / "data/v4/validation_manifest.json"
RUBRIC = ROOT / "data/v4/evaluation_rubric.json"
SIMILARITY_LIMIT = 0.82


def answer(summary: str, changes: list[str], risk: str) -> str:
    bullets = "\n".join(f"- {change}" for change in changes)
    return (
        f"## Summary\n{summary}\n## Changes\n{bullets}\n"
        "## Testing\n- Not run (not shown in diff).\n"
        f"## Risk\n{risk}"
    )


def row(diff: str, summary: str, changes: list[str], risk: str) -> dict:
    return {"messages": [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "Write the approved ITALIX PR summary for this diff.\n\n" + diff},
        {"role": "assistant", "content": answer(summary, changes, risk)},
    ]}


ROWS = [
    row("diff --git a/alerts/channel.py b/alerts/channel.py\n--- a/alerts/channel.py\n+++ b/alerts/channel.py\n@@ -2,2 +2,3 @@ def channel(team):\n+    return CHANNELS.get(team, CHANNELS[\"operations\"])", "Route unknown teams to the operations alert channel.", ["Resolve configured teams from CHANNELS.", "Fall back to CHANNELS['operations'] for an unknown team."], "Medium — unknown teams now send alerts to operations."),
    row("diff --git a/catalog/slug.ts b/catalog/slug.ts\n--- a/catalog/slug.ts\n+++ b/catalog/slug.ts\n@@ -1,2 +1,2 @@\n-export function makeSlug(value) {\n+export function normalizeSlug(value) {\n   return value.trim().toLowerCase();", "Rename makeSlug to normalizeSlug.", ["Export normalizeSlug instead of makeSlug.", "Preserve trimming and lowercasing of value."], "Medium — imports must use normalizeSlug."),
    row("diff --git a/ledger/entry.go b/ledger/entry.go\n--- a/ledger/entry.go\n+++ b/ledger/entry.go\n@@ -5,2 +5,3 @@ func Public(entry Entry) Entry {\n+    return Without(entry, \"internal_note\")\n }", "Remove internal_note from public ledger entries.", ["Call Without with entry and internal_note.", "Return the filtered entry from Public."], "Low — public output omits internal_note."),
    row("diff --git a/config/timeout.rb b/config/timeout.rb\n--- a/config/timeout.rb\n+++ b/config/timeout.rb\n@@ -2,3 +2,3 @@ def timeout\n-  45\n+  20\n end", "Reduce the configured timeout from 45 to 20.", ["Return 20 instead of 45 from timeout."], "Medium — operations have less time to complete."),
    row("diff --git a/images/format.py b/images/format.py\n--- a/images/format.py\n+++ b/images/format.py\n@@ -3,2 +3,3 @@ def output_format(name):\n+    return FORMATS.get(name) or FORMATS[\"webp\"]", "Use webp when an image format is unavailable.", ["Use FORMATS.get(name) when it returns a format.", "Fall back to FORMATS['webp'] otherwise."], "Medium — unsupported formats now produce webp output."),
    row("diff --git a/search/limits.ts b/search/limits.ts\n--- a/search/limits.ts\n+++ b/search/limits.ts\n@@ -1,3 +1,4 @@\n export const LIMITS = {\n+  autocomplete: 8,\n   results: 50,\n };", "Add an autocomplete result limit.", ["Set LIMITS.autocomplete to 8.", "Keep the existing results limit at 50."], "Low — autocomplete can return at most the configured value."),
    row("diff --git a/billing/currency.go b/billing/currency.go\n--- a/billing/currency.go\n+++ b/billing/currency.go\n@@ -4,2 +4,3 @@ func Currency(country string) string {\n+    return Coalesce(countryCurrencies[country], \"USD\")\n }", "Default billing currency to USD when a country has no mapping.", ["Prefer countryCurrencies[country].", "Use USD as the Coalesce fallback."], "Medium — unmapped countries are billed in USD."),
    row("diff --git a/export/header.rb b/export/header.rb\n--- a/export/header.rb\n+++ b/export/header.rb\n@@ -1,2 +1,2 @@\n-def csv_header(columns)\n+def export_header(columns)\n   columns.join(',')", "Rename csv_header to export_header.", ["Replace the csv_header declaration with export_header.", "Keep joining columns with a comma."], "Medium — callers must migrate to export_header."),
    row("diff --git a/profile/view.py b/profile/view.py\n--- a/profile/view.py\n+++ b/profile/view.py\n@@ -4,2 +4,3 @@ def public_profile(profile):\n+    return retain(profile, [\"handle\", \"avatar_url\"])", "Return only public profile fields.", ["Call retain with profile, handle, and avatar_url.", "Return the retained fields from public_profile."], "Low — other profile fields are excluded."),
    row("diff --git a/worker/concurrency.ts b/worker/concurrency.ts\n--- a/worker/concurrency.ts\n+++ b/worker/concurrency.ts\n@@ -1,3 +1,3 @@\n-export const MAX_WORKERS = 12;\n+export const MAX_WORKERS = 6;", "Reduce MAX_WORKERS from 12 to 6.", ["Export 6 as MAX_WORKERS instead of 12."], "Medium — the worker processes fewer tasks concurrently."),
    row("diff --git a/checkout/provider.py b/checkout/provider.py\n--- a/checkout/provider.py\n+++ b/checkout/provider.py\n@@ -2,2 +2,3 @@ def provider(region):\n+    return PROVIDERS.get(region, PROVIDERS[\"global\"])", "Use the global checkout provider for unknown regions.", ["Resolve known regions from PROVIDERS.", "Fall back to PROVIDERS['global'] for an unknown region."], "High — fallback selection affects payment routing."),
    row("diff --git a/audit/event.go b/audit/event.go\n--- a/audit/event.go\n+++ b/audit/event.go\n@@ -3,2 +3,3 @@ func Safe(event Event) Event {\n+    return DropFields(event, \"access_token\", \"refresh_token\")\n }", "Remove authentication tokens from safe audit events.", ["Call DropFields for access_token and refresh_token.", "Return the filtered event from Safe."], "Low — safe audit output excludes the named token fields."),
    row("diff --git a/parser/mode.rb b/parser/mode.rb\n--- a/parser/mode.rb\n+++ b/parser/mode.rb\n@@ -2,3 +2,3 @@ def parse_mode\n-  :lenient\n+  :strict\n end", "Change parse_mode from lenient to strict.", ["Return :strict instead of :lenient."], "Medium — previously accepted input may now be rejected."),
    row("diff --git a/report/name.ts b/report/name.ts\n--- a/report/name.ts\n+++ b/report/name.ts\n@@ -4,2 +4,3 @@ export function reportName(kind) {\n+  return NAMES[kind] ?? NAMES.summary;\n }", "Use the summary report name for unknown kinds.", ["Return NAMES[kind] when present.", "Fall back to NAMES.summary otherwise."], "Low — unknown report kinds receive the summary name."),
    row("diff --git a/queue/priority.py b/queue/priority.py\n--- a/queue/priority.py\n+++ b/queue/priority.py\n@@ -1,3 +1,4 @@\n PRIORITY = {\n+    \"incident\": 100,\n     \"normal\": 10,\n }", "Add an incident queue priority.", ["Set PRIORITY['incident'] to 100.", "Keep PRIORITY['normal'] at 10."], "Medium — incident work receives a higher numeric priority."),
    row("diff --git a/network/port.go b/network/port.go\n--- a/network/port.go\n+++ b/network/port.go\n@@ -2,3 +2,3 @@ func DefaultPort() int {\n-    return 8080\n+    return 8443\n }", "Change DefaultPort from 8080 to 8443.", ["Return port 8443 instead of 8080."], "Medium — clients must connect to the new default port."),
]


def tokens(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9_]+", value.lower()))


train_rows = [json.loads(line) for line in TRAIN.read_text(encoding="utf-8").splitlines()]
train_prompts = [record["messages"][1]["content"] for record in train_rows]
valid_prompts = [record["messages"][1]["content"] for record in ROWS]
if len(valid_prompts) != len(set(valid_prompts)):
    raise SystemExit("duplicate independent validation prompt")

maximum_similarity = 0.0
for index, record in enumerate(ROWS, 1):
    user = record["messages"][1]["content"]
    expected = record["messages"][2]["content"]
    result = score_response(expected, expected, user)
    if not result["passed"]:
        raise SystemExit(f"validation label {index} fails frozen rubric: {result}")
    left = tokens(user)
    for training_prompt in train_prompts:
        right = tokens(training_prompt)
        similarity = len(left & right) / len(left | right)
        maximum_similarity = max(maximum_similarity, similarity)
        if similarity >= SIMILARITY_LIMIT:
            raise SystemExit(f"train/validation leakage at case {index}: {similarity:.3f}")

payload = "\n".join(json.dumps(record, ensure_ascii=False) for record in ROWS) + "\n"
OUT.write_text(payload, encoding="utf-8")
rubric = {
    "version": "v4-independent-1",
    "frozen_before_training": True,
    "cases": len(ROWS),
    "decoding": {"temperature": 0.0, "max_tokens": 160, "repetition_penalty": 1.05, "repetition_context_size": 64},
    "gates": {"all_headings_once_in_order": True, "exact_testing_line": "- Not run (not shown in diff).", "maximum_repetition_ratio": 0.12, "minimum_content_recall": 0.32, "minimum_identifier_recall": 0.60, "unsupported_claims_allowed": 0, "missing_fallback_values_allowed": 0},
    "qualification": "candidate must pass all cases and strictly exceed the production-scaffold baseline",
}
RUBRIC.write_text(json.dumps(rubric, indent=2) + "\n", encoding="utf-8")
manifest = {
    "validation_sha256": hashlib.sha256(OUT.read_bytes()).hexdigest(),
    "rubric_sha256": hashlib.sha256(RUBRIC.read_bytes()).hexdigest(),
    "train_sha256": hashlib.sha256(TRAIN.read_bytes()).hexdigest(),
    "validation_cases": len(ROWS),
    "train_cases": len(train_rows),
    "maximum_train_validation_token_jaccard": round(maximum_similarity, 6),
    "sealed_holdouts_opened": False,
}
MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
print(json.dumps(manifest, indent=2))
