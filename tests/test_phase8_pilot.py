import hashlib
import json
from pathlib import Path

from italix.hybrid_triage import hybrid_triage, patch_evidence


def test_pilot_matches_published_labels_and_evidence():
    pilot = Path(__file__).resolve().parents[1] / "data/phase8/pilot-v1.jsonl"
    raw = pilot.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == pilot.with_name("SHA256SUMS").read_text().split()[0]
    rows = [json.loads(line) for line in raw.splitlines()]
    assert 100 <= len(rows) <= 200
    assert len({row["id"] for row in rows}) == len({row["diff"] for row in rows}) == len(rows)
    for row in rows:
        output = hybrid_triage(row["diff"], explain=False, engine=None)
        assert output["result"] == row["policy"]["result"], row["id"]
        assert output["abstention_reason"] == row["policy"]["abstention_reason"], row["id"]
        if output["abstention_reason"] != "malformed_or_truncated_hunk":
            _, excerpts = patch_evidence(row["diff"])
            for item in row["semantic"]["evidence"]:
                for operation, key in (("-", "removed"), ("+", "added")):
                    assert any(e["path"] == item["path"] and e["operation"] == operation
                               and e["text"] == item[key] for e in excerpts), row["id"]
