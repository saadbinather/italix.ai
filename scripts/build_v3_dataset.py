"""Build audited v3 train/dev/holdout splits without reading the legacy test set."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from italix.pr_summary import SYSTEM_PROMPT

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data/v3"


def target(summary: str, changes: list[str], risk: str) -> str:
    bullets = "\n".join(f"- {change}" for change in changes)
    return (
        f"## Summary\n{summary}\n## Changes\n{bullets}\n"
        "## Testing\n- Not run (not shown in diff).\n"
        f"## Risk\n{risk}"
    )


def record(diff: str, summary: str, changes: list[str], risk: str) -> dict:
    return {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": "Write the approved ITALIX PR summary for this diff.\n\n" + diff,
            },
            {"role": "assistant", "content": target(summary, changes, risk)},
        ]
    }


def corrected_existing(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        source = json.loads(line)
        user, assistant = source["messages"]
        before, marker, remainder = assistant["content"].partition("## Testing")
        _, risk_marker, risk = remainder.partition("## Risk")
        if not marker or not risk_marker:
            raise ValueError(f"invalid headings in {path}")
        content = before + "## Testing\n- Not run (not shown in diff).\n## Risk" + risk
        rows.append(
            {
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    user,
                    {"role": "assistant", "content": content},
                ]
            }
        )
    return rows


NEW_TRAIN = [
    record("diff --git a/api/limits.py b/api/limits.py\n--- a/api/limits.py\n+++ b/api/limits.py\n@@ -2,2 +2,4 @@ def limit(plan):\n+    if plan == \"pro\":\n+        return 500\n     return 100", "Raise the API limit for pro plans.", ["Return 500 when plan is pro.", "Keep the existing 100 default for other plans."], "Medium — pro accounts can issue more requests."),
    record("diff --git a/cache/key.ts b/cache/key.ts\n--- a/cache/key.ts\n+++ b/cache/key.ts\n@@ -3,2 +3,3 @@ export function key(userId: string) {\n+  return `profile:${userId}`;\n }", "Namespace profile cache keys by user ID.", ["Return keys in the profile:<userId> format."], "Low — changes the cache-key format for profile entries."),
    record("diff --git a/jobs/lease.py b/jobs/lease.py\n--- a/jobs/lease.py\n+++ b/jobs/lease.py\n@@ -8,2 +8,4 @@ def acquire(job):\n+    expires_at = clock.now() + timedelta(seconds=45)\n+    return leases.insert(job.id, expires_at=expires_at)", "Add 45-second leases when workers acquire jobs.", ["Calculate expires_at from clock.now().", "Insert the job lease with the 45-second expiration."], "Medium — abandoned work can be reassigned after the new lease window."),
    record("diff --git a/images/type.go b/images/type.go\n--- a/images/type.go\n+++ b/images/type.go\n@@ -4,2 +4,4 @@ func Allowed(kind string) bool {\n+    _, ok := allowedTypes[kind]\n+    return ok\n }", "Validate image types against allowedTypes.", ["Look up kind in allowedTypes.", "Return whether the type exists in the map."], "Low — unknown image types are rejected by the validator."),
    record("diff --git a/orders/currency.rb b/orders/currency.rb\n--- a/orders/currency.rb\n+++ b/orders/currency.rb\n@@ -3,2 +3,3 @@ def currency(code)\n+  SUPPORTED.fetch(code, SUPPORTED['USD'])\n end", "Default unsupported currency codes to USD.", ["Resolve code from SUPPORTED.", "Fall back to SUPPORTED['USD'] when code is unknown."], "Medium — unsupported currencies now use USD semantics."),
    record("diff --git a/events/schema.py b/events/schema.py\n--- a/events/schema.py\n+++ b/events/schema.py\n@@ -9,2 +9,4 @@ def validate(event):\n+    if event.version != 2:\n+        raise InvalidSchema(\"expected version 2\")\n     return event", "Require version 2 event payloads.", ["Raise InvalidSchema when event.version is not 2.", "Preserve the event return for valid payloads."], "Medium — older event versions will be rejected."),
    record("diff --git a/reports/name.ts b/reports/name.ts\n--- a/reports/name.ts\n+++ b/reports/name.ts\n@@ -5,2 +5,3 @@ export const filename = (id: string) => {\n+  return `report-${id}.csv`;\n };", "Generate CSV report filenames from report IDs.", ["Return filenames in the report-<id>.csv format."], "Low — only generated report names change."),
    record("diff --git a/sessions/idle.py b/sessions/idle.py\n--- a/sessions/idle.py\n+++ b/sessions/idle.py\n@@ -12,2 +12,4 @@ def expired(session, now):\n+    idle_for = now - session.last_seen_at\n+    return idle_for > timedelta(minutes=20)", "Expire sessions after 20 minutes of inactivity.", ["Calculate idle_for from last_seen_at.", "Return true when inactivity exceeds 20 minutes."], "Medium — idle sessions now expire automatically."),
    record("diff --git a/search/filter.go b/search/filter.go\n--- a/search/filter.go\n+++ b/search/filter.go\n@@ -7,2 +7,4 @@ func Filter(q Query) Query {\n+    q.Limit = min(q.Limit, 50)\n+    return q\n }", "Cap search query limits at 50.", ["Set q.Limit to the smaller of its current value and 50.", "Return the bounded query."], "Low — requests above 50 results are reduced."),
    record("diff --git a/profile/display.py b/profile/display.py\n--- a/profile/display.py\n+++ b/profile/display.py\n@@ -2,2 +2,3 @@ def name(user):\n+    return user.display_name or user.username\n", "Fall back to username when display_name is empty.", ["Return display_name when present.", "Use username as the fallback value."], "Low — profiles without display names now show usernames."),
    record("diff --git a/audit/payload.ts b/audit/payload.ts\n--- a/audit/payload.ts\n+++ b/audit/payload.ts\n@@ -6,2 +6,3 @@ export function safe(input) {\n+  return omit(input, ['access_token', 'refresh_token']);\n }", "Remove OAuth tokens from audit payloads.", ["Omit access_token and refresh_token from the returned payload."], "Low — audit consumers no longer receive OAuth token fields."),
    record("diff --git a/queue/priority.py b/queue/priority.py\n--- a/queue/priority.py\n+++ b/queue/priority.py\n@@ -4,2 +4,3 @@ def value(name):\n+    return PRIORITIES.get(name, PRIORITIES[\"normal\"])", "Use normal priority for unknown priority names.", ["Resolve known names from PRIORITIES.", "Fall back to PRIORITIES['normal'] for unknown names."], "Low — invalid priority names now use the normal queue."),
    record("diff --git a/files/path.go b/files/path.go\n--- a/files/path.go\n+++ b/files/path.go\n@@ -11,2 +11,4 @@ func Safe(root, name string) string {\n+    clean := filepath.Base(name)\n+    return filepath.Join(root, clean)\n }", "Constrain file names to the configured root directory.", ["Reduce name to filepath.Base(name).", "Join the cleaned name to root."], "Medium — nested paths are intentionally discarded."),
    record("diff --git a/web/cors.py b/web/cors.py\n--- a/web/cors.py\n+++ b/web/cors.py\n@@ -3,2 +3,4 @@ def allowed(origin):\n+    normalized = origin.rstrip(\"/\").lower()\n+    return normalized in TRUSTED_ORIGINS", "Normalize origins before checking the CORS allowlist.", ["Remove trailing slashes and lowercase origin.", "Check the normalized value against TRUSTED_ORIGINS."], "Medium — origin matching becomes normalized and allowlist-based."),
    record("diff --git a/invoices/rounding.rb b/invoices/rounding.rb\n--- a/invoices/rounding.rb\n+++ b/invoices/rounding.rb\n@@ -5,2 +5,3 @@ def cents(amount)\n+  (amount * 100).round(half: :even)\n end", "Round invoice cents using half-even rounding.", ["Multiply amount by 100.", "Round the result with half: :even."], "High — changes monetary rounding and requires finance verification."),
    record("diff --git a/flags/cohort.ts b/flags/cohort.ts\n--- a/flags/cohort.ts\n+++ b/flags/cohort.ts\n@@ -4,2 +4,3 @@ export function bucket(id: string) {\n+  return stableHash(id) % 100;\n }", "Assign stable feature cohorts from user IDs.", ["Hash id with stableHash.", "Map the hash into 100 buckets."], "Medium — cohort assignment depends on stableHash remaining stable."),
    record("diff --git a/worker/batch.py b/worker/batch.py\n--- a/worker/batch.py\n+++ b/worker/batch.py\n@@ -10,2 +10,3 @@ def chunks(items):\n+    return [items[i:i + 25] for i in range(0, len(items), 25)]", "Split worker input into batches of 25 items.", ["Slice items in increments of 25.", "Return the resulting list of chunks."], "Low — worker calls now process bounded batches."),
    record("diff --git a/accounts/lock.go b/accounts/lock.go\n--- a/accounts/lock.go\n+++ b/accounts/lock.go\n@@ -14,2 +14,4 @@ func Failed(user *User) {\n+    user.Failures++\n+    user.Locked = user.Failures >= 5\n }", "Lock accounts after five failed attempts.", ["Increment user.Failures.", "Set user.Locked when Failures reaches 5."], "High — changes account access after repeated failures."),
    record("diff --git a/markdown/render.py b/markdown/render.py\n--- a/markdown/render.py\n+++ b/markdown/render.py\n@@ -2,2 +2,3 @@ def render(text):\n+    return sanitizer.clean(markdown(text))", "Sanitize rendered Markdown output.", ["Render text with markdown().", "Clean the rendered HTML with sanitizer.clean()."], "Medium — unsafe HTML is removed from rendered content."),
    record("diff --git a/telemetry/sample.ts b/telemetry/sample.ts\n--- a/telemetry/sample.ts\n+++ b/telemetry/sample.ts\n@@ -6,2 +6,3 @@ export function keep(id: string) {\n+  return stableHash(id) % 10 === 0;\n }", "Sample ten percent of telemetry IDs deterministically.", ["Hash id with stableHash.", "Keep IDs whose hash modulo 10 equals zero."], "Low — telemetry volume is intentionally reduced."),
]

DEV = [
    record("diff --git a/api/version.py b/api/version.py\n--- a/api/version.py\n+++ b/api/version.py\n@@ -3,2 +3,4 @@ def parse(value):\n+    if value not in {\"v1\", \"v2\"}:\n+        return \"v1\"\n     return value", "Default unknown API versions to v1.", ["Accept v1 and v2 unchanged.", "Return v1 for unsupported version values."], "Medium — unknown versions now use v1 behavior."),
    record("diff --git a/logs/redact.ts b/logs/redact.ts\n--- a/logs/redact.ts\n+++ b/logs/redact.ts\n@@ -5,2 +5,3 @@ export function redact(data) {\n+  return omit(data, ['session_id', 'device_id']);\n }", "Remove device identifiers from log data.", ["Omit session_id and device_id from returned log data."], "Low — logs no longer include the named device identifiers."),
    record("diff --git a/cart/quantity.go b/cart/quantity.go\n--- a/cart/quantity.go\n+++ b/cart/quantity.go\n@@ -8,2 +8,4 @@ func Normalize(qty int) int {\n+    if qty < 1 { return 1 }\n+    return min(qty, 20)\n }", "Keep cart quantities between 1 and 20.", ["Return 1 for quantities below one.", "Cap other quantities at 20."], "Low — invalid quantities are normalized to supported bounds."),
    record("diff --git a/links/target.rb b/links/target.rb\n--- a/links/target.rb\n+++ b/links/target.rb\n@@ -4,2 +4,3 @@ def target(name)\n+  TARGETS.fetch(name, TARGETS['overview'])\n end", "Use the overview target for unknown link names.", ["Resolve known names from TARGETS.", "Fall back to TARGETS['overview'] when a name is unknown."], "Low — unsupported links now open the overview target."),
    record("diff --git a/backup/retention.py b/backup/retention.py\n--- a/backup/retention.py\n+++ b/backup/retention.py\n@@ -6,2 +6,4 @@ def expired(snapshot, now):\n+    cutoff = now - timedelta(days=14)\n+    return snapshot.created_at < cutoff", "Expire backups older than 14 days.", ["Calculate cutoff as 14 days before now.", "Mark snapshots older than cutoff as expired."], "High — old backup snapshots become eligible for deletion."),
    record("diff --git a/headers/security.ts b/headers/security.ts\n--- a/headers/security.ts\n+++ b/headers/security.ts\n@@ -2,2 +2,3 @@ export function apply(res) {\n+  res.setHeader('X-Content-Type-Options', 'nosniff');\n }", "Add the nosniff response security header.", ["Set X-Content-Type-Options to nosniff."], "Low — responses gain an additional browser security directive."),
]

HOLDOUT = [
    record("diff --git a/regions/resolve.py b/regions/resolve.py\n--- a/regions/resolve.py\n+++ b/regions/resolve.py\n@@ -3,2 +3,3 @@ def resolve(code):\n+    return REGIONS.get(code, REGIONS[\"global\"])", "Use the global region configuration for unknown codes.", ["Resolve known codes from REGIONS.", "Fall back to REGIONS['global'] for unknown codes."], "Medium — unconfigured regions use global routing."),
    record("diff --git a/privacy/event.go b/privacy/event.go\n--- a/privacy/event.go\n+++ b/privacy/event.go\n@@ -7,2 +7,4 @@ func Safe(event Map) Map {\n+    delete(event, \"phone_number\")\n+    delete(event, \"postal_address\")\n+    return event", "Remove contact details from privacy-safe events.", ["Delete phone_number and postal_address.", "Return the remaining event fields."], "Low — safe events no longer contain the named contact fields."),
    record("diff --git a/download/size.ts b/download/size.ts\n--- a/download/size.ts\n+++ b/download/size.ts\n@@ -5,2 +5,3 @@ export function allowed(bytes: number) {\n+  return bytes <= 25 * 1024 * 1024;\n }", "Limit downloads to 25 MiB.", ["Return whether bytes is at most 25 * 1024 * 1024."], "Medium — larger downloads are now rejected."),
    record("diff --git a/tokens/expiry.py b/tokens/expiry.py\n--- a/tokens/expiry.py\n+++ b/tokens/expiry.py\n@@ -4,2 +4,3 @@ def expires(now):\n+    return now + timedelta(minutes=10)", "Set token expiration to ten minutes after creation.", ["Return now plus a 10-minute timedelta."], "Medium — generated tokens receive a short fixed lifetime."),
    record("diff --git a/navigation/page.rb b/navigation/page.rb\n--- a/navigation/page.rb\n+++ b/navigation/page.rb\n@@ -3,2 +3,3 @@ def page(name)\n+  PAGES.fetch(name, PAGES['home'])\n end", "Open the home page for unknown page names.", ["Resolve known names from PAGES.", "Fall back to PAGES['home'] for unknown names."], "Low — invalid page names now land on home."),
    record("diff --git a/metrics/tags.ts b/metrics/tags.ts\n--- a/metrics/tags.ts\n+++ b/metrics/tags.ts\n@@ -8,2 +8,3 @@ export function safe(tags) {\n+  return pick(tags, ['service', 'region', 'status']);\n }", "Restrict metric tags to three supported fields.", ["Keep only service, region, and status tags."], "Low — unsupported metric tags are discarded."),
]


def validate(name: str, rows: list[dict], expected: int) -> None:
    assert len(rows) == expected, (name, len(rows))
    seen = set()
    for index, row in enumerate(rows, 1):
        roles = [message["role"] for message in row["messages"]]
        assert roles == ["system", "user", "assistant"], (name, index, roles)
        user = row["messages"][1]["content"]
        answer = row["messages"][2]["content"]
        assert "diff --git" in user and "+++ b/" in user
        assert answer.count("## Summary") == answer.count("## Changes") == 1
        assert answer.count("## Testing") == answer.count("## Risk") == 1
        assert answer.count("- Not run (not shown in diff).") == 1
        testing = answer.partition("## Testing")[2].partition("## Risk")[0].strip()
        assert testing == "- Not run (not shown in diff)."
        digest = hashlib.sha256(user.encode()).hexdigest()
        assert digest not in seen
        seen.add(digest)


train = []
for source in ("train.jsonl", "step4_extra_train.jsonl", "step4_redaction_train.jsonl"):
    train.extend(corrected_existing(ROOT / "data" / source))
train.extend(NEW_TRAIN)
validate("train", train, 56)
validate("valid", DEV, 6)
validate("holdout", HOLDOUT, 6)

all_prompts = [row["messages"][1]["content"] for row in train + DEV + HOLDOUT]
assert len(all_prompts) == len(set(all_prompts)), "cross-split duplicate prompt"

OUT.mkdir(parents=True, exist_ok=True)
for name, rows in (("train", train), ("valid", DEV), ("holdout", HOLDOUT)):
    path = OUT / f"{name}.jsonl"
    path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n")
    print(f"{name}: {len(rows)} examples, sha256={hashlib.sha256(path.read_bytes()).hexdigest()}")

assert not (OUT / "test.jsonl").exists()
print("legacy test excluded; v3 dataset valid")
