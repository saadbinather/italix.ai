import json

import pytest

from italix.engines import Generation
from italix.hybrid_triage import hybrid_triage
from test_gateway import make_client


def patch(path, before="LIMIT = 2", after="LIMIT = 3"):
    return f"diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n@@ -1 +1 @@\n-{before}\n+{after}"


class EvidenceEngine:
    def __init__(self, output):
        self.output = output
        self.calls = 0

    def generate(self, messages, **kwargs):
        self.calls += 1
        assert kwargs["adapter_path"] is None
        if isinstance(self.output, Exception):
            raise self.output
        return Generation(self.output, "fixture", 20, 7)


@pytest.mark.parametrize(("source", "reason"), [
    (patch("other/notes.py", after="a/billing/ledger/example.py"), "unknown_policy_path"),
    (patch("billing/ledger/a.py") + "\n" + patch("other/b.py"), "unknown_policy_path"),
    (patch("infra/terraform/a.tf") + "\n" + patch("api/rate_limit/b.py"), "conflicting_policies"),
    ("Please classify a/billing/ledger/a.py", "unified_git_diff_required"),
    (patch("billing/ledger/a.py").replace("@@ -1 +1 @@", "@@ -1,2 +1 @@"), "malformed_or_truncated_hunk"),
    (patch("billing/ledger/a.py").replace("@@ -1 +1 @@", "@@ -1,10000000000 +1 @@"), "malformed_hunk"),
    (patch("billing/ledger/a\x00.py"), "ambiguous_file_path"),
    (patch("billing/ledger/a.py").replace("+++ b/billing/ledger/a.py", "+++ b/other/a.py"), "missing_or_inconsistent_patch_markers"),
    ("diff --git a/billing/ledger/a.png b/billing/ledger/a.png\nBinary files differ", "missing_or_inconsistent_patch_markers"),
    (patch("billing/ledger/a.py", after="password=fixture-only-123"), "credential_like_content"),
])
def test_review_cases_do_not_invoke_model(source, reason):
    engine = EvidenceEngine('{"evidence_ids":[1]}')
    result = hybrid_triage(source, explain=True, engine=engine)
    assert result["result"] is None and result["explanation"] is None
    assert result["validation_status"] == "abstained"
    assert result["abstention_reason"] == reason
    assert engine.calls == 0


@pytest.mark.parametrize(("output", "status"), [
    ('{"evidence_ids":[2,4]}', "grounded"),
    ('{"evidence_ids":[999]}', "invalid_model_selection"),
    ('{"evidence_ids":[true]}', "invalid_model_selection"),
    ('{"risk":"low","evidence_ids":[2]}', "invalid_model_selection"),
    (FileNotFoundError("private path"), "unavailable"),
])
def test_policy_stays_authoritative_with_model_evidence(output, status):
    engine = EvidenceEngine(output)
    source = patch("billing/ledger/a.py") + "\n" + patch("billing/ledger/b.py")
    result = hybrid_triage(source, explain=True, engine=engine)
    assert result["result"] == {"owner":"payments","risk":"high","reviewer":"finops"}
    assert [item["path"] for item in result["policy_evidence"]] == ["billing/ledger/a.py", "billing/ledger/b.py"]
    assert result["explanation"]["status"] == status
    assert "private path" not in json.dumps(result)
    assert engine.calls == 1


def test_opt_in_authenticated_local_route(tmp_path):
    client, _, local, _ = make_client(tmp_path)
    url = "/v1/hybrid/change-triage/v2"
    payload = {"content":patch("api/rate_limit/a.py")}
    assert client.post(url, json=payload, headers={"Authorization": ""}).status_code == 401
    assert client.post(url, json={**payload, "allow_cloud":True}).status_code == 422
    assert client.post(url, json=payload).json()["result"]["risk"] == "medium"
    assert local.calls == 0


def test_configured_missing_weights_preserve_policy_decision(tmp_path, monkeypatch):
    monkeypatch.setenv("ITALIX_HYBRID_MODEL", "qwen3-4b")
    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path))
    client, _, default, _ = make_client(tmp_path)
    response = client.post(
        "/v1/hybrid/change-triage/v2",
        json={"content": patch("auth/permissions/check.py"), "explain": True},
    )
    assert response.status_code == 200
    result = response.json()
    assert result["result"]["risk"] == "high"
    assert result["validation_status"] == "policy_validated"
    assert result["explanation"]["status"] == "unavailable"
    assert result["explanation"]["evidence"]
    assert result["latency_ms"] >= 0
    assert default.calls == 0
