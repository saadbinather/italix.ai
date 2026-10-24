"""Build the audited v4 PR-summary training corpus without opening sealed holdouts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from italix.evaluation import (
    invented_code_identifiers,
    invented_rename_claims,
    required_fallback_values,
    score_response,
    unsupported_behavior_claims,
)
from italix.pr_summary import SYSTEM_PROMPT


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data/v3/train.jsonl"
VALIDATION = ROOT / "data/v3/valid.jsonl"
OUT = ROOT / "data/v4/train.jsonl"


def target(summary: str, changes: list[str], risk: str) -> str:
    bullets = "\n".join(f"- {change}" for change in changes)
    return (
        f"## Summary\n{summary}\n## Changes\n{bullets}\n"
        "## Testing\n- Not run (not shown in diff).\n"
        f"## Risk\n{risk}"
    )


def record(diff: str, summary: str, changes: list[str], risk: str) -> dict:
    return {"messages": [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "Write the approved ITALIX PR summary for this diff.\n\n" + diff},
        {"role": "assistant", "content": target(summary, changes, risk)},
    ]}


CORRECTIONS = {
    10: target(
        "Reject uploads larger than 10 MiB before storage.save runs.",
        ["Raise PayloadTooLarge when file.size exceeds 10 * 1024 * 1024.",
         "Keep storage.save for uploads within the limit."],
        "Medium — oversized uploads now raise PayloadTooLarge.",
    ),
    11: target(
        "Write CLI export rows through atomic_write.",
        ["Open output with atomic_write in write mode.",
         "Pass the returned handle to write_rows instead of output."],
        "Low — changes the writer used by CLI exports.",
    ),
    12: target(
        "Record HTTP latency by route name and request method.",
        ["Use unknown when request.route.name is empty.",
         "Observe request.elapsed with route and method labels."],
        "Low — adds route and method dimensions to latency observations.",
    ),
}


NEW_TRAIN = [
    # Real renames: both removed and added declarations provide rename evidence.
    record("diff --git a/auth/check.py b/auth/check.py\n--- a/auth/check.py\n+++ b/auth/check.py\n@@ -1,2 +1,2 @@\n-def can_login(user):\n+def is_login_allowed(user):\n     return user.active", "Rename can_login to is_login_allowed.", ["Replace the can_login declaration with is_login_allowed.", "Keep the user.active return behavior."], "Medium — callers must use the new function name."),
    record("diff --git a/cache/store.ts b/cache/store.ts\n--- a/cache/store.ts\n+++ b/cache/store.ts\n@@ -2,2 +2,2 @@\n-export function putEntry(key, value) {\n+export function saveEntry(key, value) {\n   return client.set(key, value);", "Rename putEntry to saveEntry.", ["Export saveEntry instead of putEntry.", "Keep client.set(key, value) unchanged."], "Medium — imports of putEntry must change."),
    record("diff --git a/jobs/state.go b/jobs/state.go\n--- a/jobs/state.go\n+++ b/jobs/state.go\n@@ -3,2 +3,2 @@\n-func Pending(job Job) bool {\n+func IsPending(job Job) bool {\n     return job.Status == \"pending\"", "Rename Pending to IsPending.", ["Replace the Pending declaration with IsPending.", "Preserve the pending-status comparison."], "Medium — Go callers must use IsPending."),
    record("diff --git a/cart/total.rb b/cart/total.rb\n--- a/cart/total.rb\n+++ b/cart/total.rb\n@@ -1,2 +1,2 @@\n-def sum(items)\n+def subtotal(items)\n   items.sum(&:price)", "Rename sum to subtotal.", ["Replace the sum method declaration with subtotal.", "Keep summing item prices."], "Medium — callers of sum must migrate to subtotal."),

    # Helper calls are additions, not renames.
    record("diff --git a/users/public.py b/users/public.py\n--- a/users/public.py\n+++ b/users/public.py\n@@ -4,2 +4,3 @@ def public(user):\n+    return select_fields(user, [\"id\", \"display_name\"])\n ", "Return selected public user fields.", ["Call select_fields with id and display_name.", "Return the helper result from public."], "Low — other user fields are excluded from this result."),
    record("diff --git a/http/body.ts b/http/body.ts\n--- a/http/body.ts\n+++ b/http/body.ts\n@@ -5,2 +5,3 @@ export function body(input) {\n+  return encodeJson(input);\n }", "Encode HTTP body input as JSON.", ["Call encodeJson with input.", "Return the encoded value from body."], "Low — body now returns the encoder output."),
    record("diff --git a/photos/thumb.go b/photos/thumb.go\n--- a/photos/thumb.go\n+++ b/photos/thumb.go\n@@ -6,2 +6,3 @@ func Thumb(image Image) Image {\n+    return Resize(image, 160, 160)\n }", "Resize thumbnails to 160 by 160.", ["Call Resize with image, width 160, and height 160.", "Return the resized image from Thumb."], "Low — generated thumbnail dimensions become fixed."),
    record("diff --git a/payments/mask.rb b/payments/mask.rb\n--- a/payments/mask.rb\n+++ b/payments/mask.rb\n@@ -3,2 +3,3 @@ def public_card(card)\n+  pick(card, :brand, :last4)\n end", "Limit public card data to brand and last4.", ["Call pick with card, brand, and last4."], "Low — other card fields are excluded."),

    # Explicit fallback behavior with distinct values and syntax.
    record("diff --git a/themes/palette.py b/themes/palette.py\n--- a/themes/palette.py\n+++ b/themes/palette.py\n@@ -2,2 +2,3 @@ def palette(name):\n+    return PALETTES.get(name, PALETTES[\"neutral\"])", "Use the neutral palette for unknown names.", ["Resolve known names from PALETTES.", "Fall back to PALETTES['neutral'] when name is unknown."], "Low — invalid palette names use neutral colors."),
    record("diff --git a/mail/sender.rb b/mail/sender.rb\n--- a/mail/sender.rb\n+++ b/mail/sender.rb\n@@ -3,2 +3,3 @@ def sender(key)\n+  SENDERS.fetch(key, SENDERS['support'])\n end", "Use the support sender for unknown keys.", ["Resolve known keys from SENDERS.", "Fall back to SENDERS['support'] when key is unknown."], "Medium — unrecognized sender keys use the support identity."),
    record("diff --git a/locale/direction.ts b/locale/direction.ts\n--- a/locale/direction.ts\n+++ b/locale/direction.ts\n@@ -2,2 +2,3 @@ export function direction(locale) {\n+  return DIRECTIONS[locale] ?? DIRECTIONS.en;\n }", "Use the English direction for unknown locales.", ["Return DIRECTIONS[locale] when present.", "Fall back to DIRECTIONS.en otherwise."], "Low — unsupported locales use English text direction."),
    record("diff --git a/storage/bucket.go b/storage/bucket.go\n--- a/storage/bucket.go\n+++ b/storage/bucket.go\n@@ -4,2 +4,3 @@ func Bucket(region string) string {\n+    return FirstNonEmpty(buckets[region], buckets[\"primary\"])\n }", "Use the primary bucket when a region has no bucket.", ["Prefer buckets[region].", "Fall back to buckets['primary'] through FirstNonEmpty."], "Medium — unconfigured regions write to the primary bucket."),
    record("diff --git a/editor/font.py b/editor/font.py\n--- a/editor/font.py\n+++ b/editor/font.py\n@@ -3,2 +3,3 @@ def font(name):\n+    return FONTS.get(name) or FONTS[\"sans\"]", "Use the sans font when a named font is unavailable.", ["Return FONTS.get(name) when available.", "Use FONTS['sans'] as the fallback."], "Low — unknown font names render with sans."),
    record("diff --git a/video/codec.ts b/video/codec.ts\n--- a/video/codec.ts\n+++ b/video/codec.ts\n@@ -3,2 +3,3 @@ export function codec(name) {\n+  return CODECS.get(name, CODECS.get('h264'));\n }", "Use h264 when a codec name is unknown.", ["Resolve name through CODECS.get.", "Fall back to CODECS.get('h264')."], "Medium — unsupported codec names use h264."),

    # Mixed additions/removals: describe only evidence in the patch.
    record("diff --git a/api/retries.py b/api/retries.py\n--- a/api/retries.py\n+++ b/api/retries.py\n@@ -2,3 +2,3 @@ def attempts():\n-    return 5\n+    return 3", "Reduce API retry attempts from 5 to 3.", ["Return 3 attempts instead of 5."], "Medium — transient failures receive fewer retries."),
    record("diff --git a/logging/level.ts b/logging/level.ts\n--- a/logging/level.ts\n+++ b/logging/level.ts\n@@ -1,3 +1,3 @@\n-export const DEFAULT_LEVEL = 'debug';\n+export const DEFAULT_LEVEL = 'info';", "Change DEFAULT_LEVEL from debug to info.", ["Export info as the new DEFAULT_LEVEL."], "Low — default logs become less verbose."),
    record("diff --git a/orders/window.go b/orders/window.go\n--- a/orders/window.go\n+++ b/orders/window.go\n@@ -4,3 +4,4 @@ func Open(hour int) bool {\n-    return hour >= 8\n+    return hour >= 8 && hour < 18\n }", "Close the order window at hour 18.", ["Keep the lower bound at hour 8.", "Require hour to be below 18."], "Medium — orders at or after hour 18 are rejected."),
    record("diff --git a/search/mode.rb b/search/mode.rb\n--- a/search/mode.rb\n+++ b/search/mode.rb\n@@ -2,3 +2,3 @@ def mode\n-  :fuzzy\n+  :exact\n end", "Change the search mode from fuzzy to exact.", ["Return :exact instead of :fuzzy."], "Medium — matching behavior becomes exact."),
    record("diff --git a/session/cookie.py b/session/cookie.py\n--- a/session/cookie.py\n+++ b/session/cookie.py\n@@ -3,4 +3,4 @@ OPTIONS = {\n-    \"max_age\": 86400,\n-    \"secure\": False,\n+    \"max_age\": 3600,\n+    \"secure\": True,\n }", "Shorten session cookies and require secure transport.", ["Reduce max_age from 86400 to 3600.", "Set secure to true instead of false."], "Medium — sessions expire sooner and require HTTPS."),
    record("diff --git a/metrics/sample.ts b/metrics/sample.ts\n--- a/metrics/sample.ts\n+++ b/metrics/sample.ts\n@@ -3,3 +3,3 @@ export const RATE =\n-  0.25;\n+  0.10;", "Reduce RATE from 0.25 to 0.10.", ["Set RATE to 0.10 instead of 0.25."], "Low — fewer metric events are sampled."),
]


def prompt(row: dict) -> str:
    return row["messages"][1]["content"]


def validate(rows: list[dict]) -> None:
    if len(rows) != 76:
        raise ValueError(f"expected 76 training examples, found {len(rows)}")
    prompts = [prompt(row) for row in rows]
    if len(prompts) != len(set(prompts)):
        raise ValueError("duplicate v4 training prompt")
    for index, row in enumerate(rows, 1):
        roles = [message.get("role") for message in row.get("messages", [])]
        if roles != ["system", "user", "assistant"]:
            raise ValueError(f"row {index}: invalid roles")
        user, answer = row["messages"][1]["content"], row["messages"][2]["content"]
        result = score_response(answer, answer, user)
        label_gates = (
            result["format_ok"]
            and result["testing_ok"]
            and result["repetition_ratio"] <= 0.12
            and not result["unsupported_hits"]
            and not result["invented_rename_claims"]
            and not result["invented_identifiers"]
            and not result["unsupported_behavior_claims"]
            and not result["missing_fallback_values"]
        )
        if not label_gates:
            raise ValueError(f"row {index}: label fails deterministic quality gates: {result}")
        evidence_errors = {
            "renames": invented_rename_claims(answer, "", user),
            "identifiers": invented_code_identifiers(answer, "", user),
            "behavior": unsupported_behavior_claims(answer, "", user),
            "fallbacks": sorted(v for v in required_fallback_values(user) if v not in answer.lower()),
        }
        if any(evidence_errors.values()):
            raise ValueError(f"row {index}: unsupported label evidence: {evidence_errors}")

    validation_prompts = {
        prompt(json.loads(line)) for line in VALIDATION.read_text(encoding="utf-8").splitlines()
    }
    overlap = validation_prompts & set(prompts)
    if overlap:
        raise ValueError(f"validation leakage: {len(overlap)} exact prompt matches")

    def tokens(value: str) -> set[str]:
        return set(re.findall(r"[a-z0-9_]+", value.lower()))

    for train_prompt in prompts:
        train_tokens = tokens(train_prompt)
        for valid_prompt in validation_prompts:
            valid_tokens = tokens(valid_prompt)
            similarity = len(train_tokens & valid_tokens) / len(train_tokens | valid_tokens)
            if similarity >= 0.82:
                raise ValueError(f"near-duplicate validation prompt: {similarity:.2f}")


base = [json.loads(line) for line in SOURCE.read_text(encoding="utf-8").splitlines()]
for line_number, replacement in CORRECTIONS.items():
    base[line_number - 1]["messages"][2]["content"] = replacement
rows = base + NEW_TRAIN
validate(rows)

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n")
print(f"v4 train: {len(rows)} examples")
print(f"corrected labels: {sorted(CORRECTIONS)}")
print(f"new team-authored examples: {len(NEW_TRAIN)}")
print(f"sha256={hashlib.sha256(OUT.read_bytes()).hexdigest()}")
print("validation leakage: none (exact and token similarity < 0.82)")
print("sealed holdout: not read; existing v3 files unchanged")
