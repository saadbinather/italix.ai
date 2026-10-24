from __future__ import annotations

import json
import sqlite3

import httpx
import pytest
from fastapi.testclient import TestClient

from italix.api import create_app
from italix.engines import Generation, GeminiEngine, GroqEngine
from italix.evaluation import ServerEvaluator


OPERATOR_HEADERS = {"Authorization": "Bearer test-operator-token-0123456789abcde"}


class FakeEngine:
    def __init__(self, text="## Summary\nSynthetic response", model="fake-local", configured=True):
        self.text = text
        self.model = model
        self.configured = configured
        self.calls = 0
        self.adapter_paths = []

    def generate(self, messages, max_tokens, temperature, adapter_path=None):
        self.calls += 1
        self.adapter_paths.append(adapter_path)
        return Generation(self.text, self.model, 12, 5)


class FailingEngine(FakeEngine):
    def generate(self, messages, max_tokens, temperature, adapter_path=None):
        self.calls += 1
        raise RuntimeError("synthetic local failure")


class FakeEvaluator:
    def __init__(self, qualified=True):
        self.qualified = qualified

    def compare(self, candidate_path, split="valid", workload="pr_summary"):
        return {
            "split": split,
            "qualified": self.qualified,
            "candidates": [
                {"name": "base_scaffold", "passed": 2, "total": 3},
                {"name": "candidate", "passed": 3 if self.qualified else 2, "total": 3},
            ],
        }


class FakeTrainingRunner:
    def __init__(self):
        self.calls = []

    def execute(self, job_id, candidate_id):
        self.calls.append((job_id, candidate_id))
        return {"id": job_id, "candidate_id": candidate_id, "status": "completed"}

    def public_config(self, workload="pr_summary"):
        return {"engine": "fake", "rank": 4, "workload": workload}


def make_client(
    tmp_path, *, local=None, gemini=None, groq=None, evaluator=None, training_runner=None
):
    local = local or FakeEngine()
    gemini = gemini or FakeEngine(model="mock-gemini", configured=False)
    groq = groq or FakeEngine(model="mock-groq", configured=False)
    app = create_app(
        database_path=tmp_path / "italix.db",
        local_engine=local,
        gemini_engine=gemini,
        groq_engine=groq,
        evaluation_runner=evaluator or FakeEvaluator(),
        training_runner=training_runner,
    )
    return TestClient(app, headers=OPERATOR_HEADERS), app, local, gemini


def request_body(*, capture=False, model="italix-auto", allow_cloud=False):
    return {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": "Summarize this PR:\n\ndiff --git a/a.py b/a.py\n+return 1",
            }
        ],
        "workload": "pr_summary",
        "capture": capture,
        "allow_cloud": allow_cloud,
    }


def test_local_openai_response_and_redacted_trace(tmp_path):
    client, _, local, _ = make_client(tmp_path)
    response = client.post("/v1/chat/completions", json=request_body())
    assert response.status_code == 200
    body = response.json()
    assert body["object"] == "chat.completion"
    assert body["italix"]["route"] == "local"
    assert body["italix"]["registry_model"] == "qwen-base"
    assert body["usage"]["total_tokens"] == 17
    assert local.calls == 1
    trace = client.get(f"/v1/traces/{body['italix']['trace_id']}").json()
    assert trace["capture_enabled"] == 0
    assert trace["prompt_json"] is None
    assert trace["response_text"] is None


def test_inactive_deterministic_candidate_is_explicitly_invokable_and_traced(tmp_path):
    client, app, local, _ = make_client(tmp_path)
    body = request_body(model="pr-summary-deterministic-v1")
    body["messages"][0]["content"] = (
        "Summarize this PR:\n\ndiff --git a/config.py b/config.py\n"
        "--- a/config.py\n+++ b/config.py\n@@ -1 +1 @@\n-LIMIT = 8\n+LIMIT = 4"
    )
    response = client.post("/v1/chat/completions", json=body)
    assert response.status_code == 200
    result = response.json()
    assert result["model"] == "pr-summary-deterministic-v1"
    assert result["italix"]["registry_model"] == "pr-summary-deterministic-v1"
    assert result["italix"]["route"] == "deterministic"
    assert result["italix"]["adapter_used"] is False
    assert result["italix"]["abstained"] is False
    assert result["italix"]["deterministic_validation"]["valid"] is True
    assert "Set LIMIT to 4 instead of 8." in result["choices"][0]["message"]["content"]
    assert local.calls == 0
    trace = client.get(f"/v1/traces/{result['italix']['trace_id']}").json()
    assert trace["selected_model"] == "pr-summary-deterministic-v1"
    assert trace["route"] == "deterministic"
    assert trace["validation"]["abstained"] is False
    assert app.state.database.active_model("pr_summary")["id"] == "qwen-base"


def test_deterministic_candidate_abstains_on_binary_and_keeps_queue_isolated(tmp_path):
    client, app, local, _ = make_client(tmp_path)
    body = request_body(capture=True, model="pr-summary-deterministic-v1")
    body["messages"][0]["content"] = (
        "diff --git a/logo.png b/logo.png\n"
        "Binary files /dev/null and b/logo.png differ"
    )
    result = client.post("/v1/chat/completions", json=body).json()
    assert result["italix"]["abstained"] is True
    assert result["italix"]["abstention_reasons"] == ["binary content is not inspected"]
    assert local.calls == 0
    feedback = client.post(
        f"/v1/traces/{result['italix']['trace_id']}/feedback", json={"action": "approve"}
    )
    assert feedback.status_code == 200
    assert feedback.json()["feedback_status"] == "approved"
    assert feedback.json()["queued"] is False
    assert client.get("/v1/training/queue?workload=pr_summary").json()["pending"] == 0
    with app.state.database.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM feedback").fetchone()[0] == 1


def test_deterministic_candidate_can_be_audited_and_rolled_back(tmp_path):
    client, app, local, _ = make_client(tmp_path)
    candidate = app.state.database.model("pr-summary-deterministic-v1")
    assert candidate["kind"] == "system"
    assert candidate["status"] == "validation_passed"
    assert candidate["active"] == 0
    activated = client.post(
        "/v1/models/pr-summary-deterministic-v1/activate", json={"workload": "pr_summary"}
    )
    assert activated.status_code == 200
    assert activated.json()["active"] == 1
    body = request_body()
    body["messages"][0]["content"] = (
        "Summarize this PR:\n\ndiff --git a/config.py b/config.py\n"
        "--- a/config.py\n+++ b/config.py\n@@ -1 +1 @@\n-LIMIT = 8\n+LIMIT = 4"
    )
    inference = client.post("/v1/chat/completions", json=body)
    assert inference.status_code == 200
    assert inference.json()["italix"]["route"] == "deterministic"
    assert inference.json()["model"] == "pr-summary-deterministic-v1"
    assert local.calls == 0
    rolled_back = client.post("/v1/routes/pr_summary/rollback")
    assert rolled_back.status_code == 200
    assert rolled_back.json()["id"] == "qwen-base"
    history = client.get("/v1/routes/pr_summary/history").json()["data"]
    assert [item["action"] for item in history[:2]] == ["rollback", "activate"]


def test_approval_and_correction_enter_queue_but_rejection_does_not(tmp_path):
    client, _, _, _ = make_client(tmp_path)
    first = client.post("/v1/chat/completions", json=request_body(capture=True)).json()
    trace_id = first["italix"]["trace_id"]
    approved = client.post(f"/v1/traces/{trace_id}/feedback", json={"action": "approve"})
    assert approved.status_code == 200
    assert approved.json()["queued"] is True
    assert client.get("/v1/training/queue?workload=pr_summary").json()["pending"] == 1

    corrected_text = "## Summary\nApproved correction"
    corrected = client.post(
        f"/v1/traces/{trace_id}/feedback",
        json={"action": "correct", "corrected_response": corrected_text},
    )
    assert corrected.status_code == 200
    with sqlite3.connect(tmp_path / "italix.db") as connection:
        stored = connection.execute(
            "SELECT approved_response FROM training_queue WHERE trace_id = ?", (trace_id,)
        ).fetchone()[0]
    assert stored == corrected_text

    second = client.post("/v1/chat/completions", json=request_body(capture=True)).json()
    rejected_id = second["italix"]["trace_id"]
    rejected = client.post(f"/v1/traces/{rejected_id}/feedback", json={"action": "reject"})
    assert rejected.json()["queued"] is False
    assert client.get("/v1/training/queue?workload=pr_summary").json()["pending"] == 1


def test_uncaptured_response_cannot_enter_training(tmp_path):
    client, _, _, _ = make_client(tmp_path)
    result = client.post("/v1/chat/completions", json=request_body()).json()
    response = client.post(
        f"/v1/traces/{result['italix']['trace_id']}/feedback", json={"action": "approve"}
    )
    assert response.status_code == 409
    assert client.get("/v1/training/queue").json()["pending"] == 0


def test_training_action_plans_batch_without_running_training(tmp_path):
    client, _, _, _ = make_client(tmp_path)
    result = client.post("/v1/chat/completions", json=request_body(capture=True)).json()
    client.post(f"/v1/traces/{result['italix']['trace_id']}/feedback", json={"action": "approve"})
    response = client.post(
        "/v1/training/jobs", json={"workload": "pr_summary", "minimum_examples": 1}
    )
    assert response.status_code == 202
    assert response.json()["status"] == "planned"


def test_training_queue_reports_readiness_from_requested_minimum(tmp_path):
    client, _, _, _ = make_client(tmp_path)
    empty = client.get("/v1/training/queue?workload=pr_summary&minimum_examples=1").json()
    assert empty["pending"] == 0
    assert empty["minimum_examples"] == 1
    assert empty["enough_examples"] is False

    result = client.post("/v1/chat/completions", json=request_body(capture=True)).json()
    client.post(f"/v1/traces/{result['italix']['trace_id']}/feedback", json={"action": "approve"})
    ready = client.get("/v1/training/queue?workload=pr_summary&minimum_examples=1").json()
    assert ready["pending"] == 1
    assert ready["enough_examples"] is True


def test_explicit_training_execution_calls_runner_after_queue_snapshot(tmp_path):
    runner = FakeTrainingRunner()
    client, _, _, _ = make_client(tmp_path, training_runner=runner)
    result = client.post("/v1/chat/completions", json=request_body(capture=True)).json()
    client.post(f"/v1/traces/{result['italix']['trace_id']}/feedback", json={"action": "approve"})
    response = client.post(
        "/v1/training/jobs",
        json={
            "workload": "pr_summary",
            "minimum_examples": 1,
            "candidate_id": "adapter-test",
            "execute": True,
        },
    )
    assert response.status_code == 202
    assert response.json()["status"] == "completed"
    assert runner.calls == [(1, "adapter-test")]


def test_failed_adapters_cannot_activate_and_base_rollback_is_safe(tmp_path):
    client, _, _, _ = make_client(tmp_path)
    models = {model["id"]: model for model in client.get("/v1/models").json()["data"]}
    assert models["adapter-v1"]["status"] == "experimental_failed"
    assert models["adapter-v2"]["status"] == "experimental_failed"
    assert client.post(
        "/v1/models/adapter-v2/activate", json={"workload": "pr_summary"}
    ).status_code == 409
    rollback = client.post("/v1/routes/pr_summary/rollback")
    assert rollback.status_code == 200
    assert rollback.json()["id"] == "qwen-base"


def test_only_server_qualified_adapter_can_activate_then_rollback(tmp_path):
    client, app, local, _ = make_client(tmp_path)
    with app.state.database.connect() as connection:
        connection.execute(
            """INSERT INTO models
            (id, workload, kind, status, path, metrics_json, active, created_at)
            VALUES ('adapter-v3', 'pr_summary', 'adapter', 'experimental',
            'artifacts/adapters/v3', '{}', 0, '2026-10-14T00:00:00+00:00')"""
        )
    evaluation = client.post(
        "/v1/models/adapter-v3/evaluation",
        json={"workload": "pr_summary", "split": "valid"},
    )
    assert evaluation.status_code == 200
    assert evaluation.json()["status"] == "qualified"
    activated = client.post(
        "/v1/models/adapter-v3/activate", json={"workload": "pr_summary"}
    )
    assert activated.status_code == 200
    assert activated.json()["id"] == "adapter-v3"
    completion = client.post("/v1/chat/completions", json=request_body())
    assert completion.json()["italix"]["registry_model"] == "adapter-v3"
    assert local.adapter_paths[-1] == "artifacts/adapters/v3"
    assert client.post("/v1/routes/pr_summary/rollback").json()["id"] == "qwen-base"


def test_cloud_requires_opt_in_and_mock_fallback_is_logged(tmp_path):
    gemini = FakeEngine(text="mock cloud response", model="mock-gemini", configured=True)
    client, _, _, _ = make_client(tmp_path, local=FailingEngine(), gemini=gemini)
    denied = client.post(
        "/v1/chat/completions", json=request_body(model="gemini", allow_cloud=False)
    )
    assert denied.status_code == 403
    fallback = client.post(
        "/v1/chat/completions", json=request_body(capture=True, allow_cloud=True)
    )
    assert fallback.status_code == 200
    body = fallback.json()
    assert body["italix"]["route"] == "cloud"
    assert "fallback" in body["italix"]["routing_reason"]
    assert gemini.calls == 1
    trace = client.get(f"/v1/traces/{body['italix']['trace_id']}").json()
    assert trace["route"] == "cloud"
    assert trace["selected_model"] == "gemini"


def test_health_does_not_require_cloud_keys(tmp_path):
    client, _, _, _ = make_client(tmp_path)
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    assert health.json()["cloud_calls_require_request_opt_in"] is True


def test_change_triage_has_independent_base_route_and_failed_adapter_is_blocked(tmp_path):
    client, _, local, _ = make_client(tmp_path)
    body = request_body()
    body["workload"] = "change_triage"
    response = client.post("/v1/chat/completions", json=body)
    assert response.status_code == 200
    assert response.json()["italix"]["registry_model"] == "qwen-base-triage"
    assert local.adapter_paths[-1] is None
    with client.app.state.database.connect() as connection:
        connection.execute(
            """INSERT INTO models
            (id, workload, kind, status, path, metrics_json, active, created_at)
            VALUES ('triage-failed', 'change_triage', 'adapter', 'experimental_failed',
            'artifacts/adapters/failed', '{}', 0, '2026-10-14T00:00:00+00:00')"""
        )
    blocked = client.post(
        "/v1/models/triage-failed/activate", json={"workload": "change_triage"}
    )
    assert blocked.status_code == 409
    assert client.post("/v1/routes/change_triage/rollback").json()["id"] == "qwen-base-triage"


def test_change_triage_validation_flags_model_output_without_fixing_it(tmp_path):
    invalid = '{"owner":"ITALIX","risk":"Medium","reviewer":"ITIL"}'
    client, _, _, _ = make_client(tmp_path, local=FakeEngine(text=invalid))
    body = request_body(capture=True)
    body["workload"] = "change_triage"
    body["messages"][0]["content"] = (
        "diff --git a/auth/permissions/admin.py b/auth/permissions/admin.py\n+x=1"
    )
    response = client.post("/v1/chat/completions", json=body)
    assert response.status_code == 200
    result = response.json()
    assert result["choices"][0]["message"]["content"] == invalid
    assert result["italix"]["validation"]["valid"] is False
    assert "does not match company policy" in result["italix"]["validation"]["reason"]


def test_change_triage_feedback_requires_valid_policy_correction(tmp_path):
    client, app, _, _ = make_client(tmp_path, local=FakeEngine(text='{"owner":"wrong","risk":"low","reviewer":"wrong"}'))
    body = request_body(capture=True)
    body["workload"] = "change_triage"
    body["messages"][0]["content"] = (
        "diff --git a/auth/permissions/admin.py b/auth/permissions/admin.py\n+x=1"
    )
    trace_id = client.post("/v1/chat/completions", json=body).json()["italix"]["trace_id"]

    invalid = client.post(
        f"/v1/traces/{trace_id}/feedback",
        json={
            "action": "correct",
            "corrected_response": '{"owner":"product","risk":"low","reviewer":"frontend"}',
        },
    )
    assert invalid.status_code == 422
    assert "invalid change_triage correction" in invalid.json()["detail"]
    assert client.get("/v1/training/queue?workload=change_triage").json()["pending"] == 0

    correction = '{"owner":"identity","risk":"high","reviewer":"security"}'
    accepted = client.post(
        f"/v1/traces/{trace_id}/feedback",
        json={"action": "correct", "corrected_response": correction},
    )
    assert accepted.status_code == 200
    assert accepted.json()["queued"] is True
    with app.state.database.connect() as connection:
        stored = connection.execute(
            "SELECT approved_response FROM training_queue WHERE trace_id = ?", (trace_id,)
        ).fetchone()[0]
    assert stored == correction


def test_dashboard_reads_are_aggregate_and_payload_safe(tmp_path):
    runner = FakeTrainingRunner()
    client, _, _, _ = make_client(tmp_path, training_runner=runner)
    completion = client.post("/v1/chat/completions", json=request_body(capture=True)).json()
    client.post(
        f"/v1/traces/{completion['italix']['trace_id']}/feedback", json={"action": "approve"}
    )
    overview = client.get("/v1/dashboard/overview").json()
    assert overview["total_requests"] == 1
    assert overview["local_requests"] == 1
    assert overview["captured_interactions"] == 1
    assert overview["queue_pending"] == 1
    assert overview["measured_cloud_cost_usd"] is None
    traces = client.get("/v1/traces").json()["data"]
    assert len(traces) == 1
    assert "prompt_json" not in traces[0]
    assert "response_text" not in traces[0]
    assert client.get("/v1/training/config").json()["rank"] == 4


def test_rollback_is_audited(tmp_path):
    client, _, _, _ = make_client(tmp_path)
    response = client.post("/v1/routes/pr_summary/rollback")
    assert response.status_code == 200
    history = client.get("/v1/routes/pr_summary/history").json()["data"]
    assert history[0]["model_id"] == "qwen-base"
    assert history[0]["action"] == "rollback"


def test_hybrid_triage_is_deterministic_or_abstains_without_cloud(tmp_path):
    gemini = FakeEngine(model="mock-gemini", configured=True)
    client, _, _, _ = make_client(tmp_path, gemini=gemini)
    known = client.post(
        "/v1/hybrid/change-triage",
        json={"content": "diff --git a/auth/permissions/a.py b/auth/permissions/a.py\n+x=1"},
    ).json()
    assert known["route"] == "deterministic"
    assert known["result"] == {"owner": "identity", "risk": "high", "reviewer": "security"}
    assert known["adapter_used"] is False
    assert gemini.calls == 0
    unknown = client.post(
        "/v1/hybrid/change-triage",
        json={"content": "diff --git a/search/index.py b/search/index.py\n+x=1"},
    ).json()
    assert unknown["route"] == "abstain"
    assert unknown["cloud_used"] is False
    assert gemini.calls == 0


def test_hybrid_cloud_fallback_requires_explicit_opt_in(tmp_path):
    gemini = FakeEngine(text='{"owner":"unknown"}', model="mock-gemini", configured=True)
    client, _, _, _ = make_client(tmp_path, gemini=gemini)
    fallback = client.post(
        "/v1/hybrid/change-triage",
        json={"content": "diff --git a/search/index.py b/search/index.py\n+x=1", "allow_cloud": True},
    ).json()
    assert fallback["route"] == "cloud"
    assert fallback["cloud_used"] is True
    assert gemini.calls == 1


def test_provider_timeouts_are_sanitized():
    def timeout(request):
        raise httpx.ReadTimeout("secret transport details", request=request)

    client = httpx.Client(transport=httpx.MockTransport(timeout))
    with pytest.raises(RuntimeError, match="Gemini request timed out"):
        GeminiEngine(api_key="not-a-real-key", client=client).generate(
            [{"role": "user", "content": "hello"}], 10, 0.0
        )
    with pytest.raises(RuntimeError, match="Groq request timed out"):
        GroqEngine(api_key="not-a-real-key", client=client).generate(
            [{"role": "user", "content": "hello"}], 10, 0.0
        )


def test_server_evaluator_refuses_sealed_holdout_by_default():
    with pytest.raises(PermissionError, match="sealed holdout"):
        ServerEvaluator().compare("unused", split="holdout", workload="change_triage")
