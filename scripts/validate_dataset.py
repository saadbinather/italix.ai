"""Validate schema, format, counts, and leakage for the PR-summary dataset."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
EXPECTED_COUNTS = {"train": 18, "valid": 3, "test": 3}
HEADINGS = ("## Summary", "## Changes", "## Testing", "## Risk")
NEAR_DUPLICATE_THRESHOLD = 0.82


def tokens(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9_]+", value.lower()))


def similarity(left: str, right: str) -> float:
    a, b = tokens(left), tokens(right)
    return len(a & b) / len(a | b) if a or b else 1.0


records: list[tuple[str, int, dict]] = []
errors: list[str] = []

for split, expected in EXPECTED_COUNTS.items():
    path = DATA_DIR / f"{split}.jsonl"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        errors.append(f"missing file: {path}")
        continue
    if len(lines) != expected:
        errors.append(f"{path.name}: expected {expected} lines, found {len(lines)}")
    for line_number, line in enumerate(lines, 1):
        label = f"{path.name}:{line_number}"
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"{label}: invalid JSON ({exc.msg})")
            continue
        if set(record) != {"messages"} or not isinstance(record["messages"], list):
            errors.append(f"{label}: record must contain only a messages array")
            continue
        messages = record["messages"]
        if len(messages) != 2 or [m.get("role") for m in messages] != ["user", "assistant"]:
            errors.append(f"{label}: roles must be exactly user, assistant")
            continue
        if any(set(m) != {"role", "content"} or not isinstance(m["content"], str) for m in messages):
            errors.append(f"{label}: each message needs only string role/content fields")
            continue
        user, assistant = messages[0]["content"], messages[1]["content"]
        if "diff --git" not in user or "+++ b/" not in user:
            errors.append(f"{label}: user content lacks a recognizable Git diff")
        positions = [assistant.find(heading) for heading in HEADINGS]
        if any(position < 0 for position in positions) or positions != sorted(positions):
            errors.append(f"{label}: missing or unordered output headings")
        risk = assistant.partition("## Risk")[2].strip()
        if not re.match(r"^(Low|Medium|High) — .+", risk):
            errors.append(f"{label}: invalid risk line")
        records.append((split, line_number, record))

seen: dict[str, str] = {}
for split, line_number, record in records:
    canonical = json.dumps(record, sort_keys=True)
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    label = f"{split}.jsonl:{line_number}"
    if digest in seen:
        errors.append(f"exact duplicate: {seen[digest]} and {label}")
    seen[digest] = label

for index, (split_a, line_a, record_a) in enumerate(records):
    text_a = " ".join(message["content"] for message in record_a["messages"])
    for split_b, line_b, record_b in records[index + 1 :]:
        text_b = " ".join(message["content"] for message in record_b["messages"])
        score = similarity(text_a, text_b)
        if score >= NEAR_DUPLICATE_THRESHOLD:
            errors.append(
                f"near duplicate ({score:.2f}): {split_a}.jsonl:{line_a} and "
                f"{split_b}.jsonl:{line_b}"
            )

if errors:
    raise SystemExit("Dataset validation failed:\n- " + "\n- ".join(errors))

counts = ", ".join(f"{name}={count}" for name, count in EXPECTED_COUNTS.items())
print(f"Dataset valid: {len(records)} records ({counts})")
print(f"Near-duplicate threshold: {NEAR_DUPLICATE_THRESHOLD:.2f}")
