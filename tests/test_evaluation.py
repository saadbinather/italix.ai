from __future__ import annotations

import json
from pathlib import Path

from italix.evaluation import score_response


ROOT = Path(__file__).resolve().parents[1]
ROWS = [json.loads(line) for line in (ROOT / "data/v3/valid.jsonl").read_text().splitlines()]

CASE_2_ACTUAL = """## Summary
- Update the `redact` function to remove sensitive fields from the data object.

## Changes
- Renamed the `redact` function to `omit`.
- Added a new field `['session_id', 'device_id']` to be omitted from the data.
- The updated code is now more concise and follows best practices.

## Testing
- Not run (not shown in diff).

## Risk
- Low: This change is straightforward and aligns with security best practices."""

CASE_4_ACTUAL = """## Summary
- Added a fallback value to the `TARGETS` hash in `target.rb`.
+ Corrected the `TARGETS` hash to use `fetch` instead of `merge!`, ensuring that
+ `name` is not `nil` or undefined.

## Changes
- Updated the `TARGETS` hash to use `fetch` instead of `merge!`.
+ Ensured that `name` is not `nil` or undefined by using `fetch`.

## Testing
- Not run (not shown in diff).

## Risk
- Low
- This change ensures that `name` is not `nil` or undefined, which is a small but necessary improvement."""


def _case(index: int) -> tuple[str, str]:
    messages = ROWS[index - 1]["messages"]
    return messages[-2]["content"], messages[-1]["content"]


def test_case_2_detects_invented_rename_and_unsupported_quality_claims():
    diff, expected = _case(2)
    result = score_response(CASE_2_ACTUAL, expected, diff)

    assert result["passed"] is False
    assert result["invented_rename_claims"] == [{"from": "redact", "to": "omit"}]
    assert result["invented_identifiers"] == []
    assert result["unsupported_behavior_claims"] == ["best practices", "more concise"]


def test_case_4_detects_nonexistent_identifiers_behavior_and_missing_fallback():
    diff, expected = _case(4)
    result = score_response(CASE_4_ACTUAL, expected, diff)

    assert result["passed"] is False
    assert result["invented_identifiers"] == ["merge!", "nil"]
    assert result["unsupported_behavior_claims"] == [
        "nil or undefined", "replacement of nonexistent `merge!`"
    ]
    assert result["required_fallback_values"] == ["overview"]
    assert result["missing_fallback_values"] == ["overview"]


def test_documented_expected_outputs_do_not_trigger_new_checks():
    for index in range(1, 7):
        diff, expected = _case(index)
        result = score_response(expected, expected, diff)

        assert result["invented_rename_claims"] == []
        assert result["invented_identifiers"] == []
        assert result["unsupported_behavior_claims"] == []
        assert result["missing_fallback_values"] == []


def test_supported_rename_is_not_flagged():
    diff = """diff --git a/a.py b/a.py
--- a/a.py
+++ b/a.py
@@ -1 +1 @@
-def redact(data):
+def omit(data):"""
    response = """## Summary
Rename `redact` to `omit`.
## Changes
- Rename `redact` to `omit`.
## Testing
- Not run (not shown in diff).
## Risk
Low — name-only change."""
    result = score_response(response, response, diff)

    assert result["invented_rename_claims"] == []
    assert result["invented_identifiers"] == []
