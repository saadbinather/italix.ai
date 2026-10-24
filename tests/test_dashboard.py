from __future__ import annotations

import json
from pathlib import Path

import httpx
from streamlit.testing.v1 import AppTest


def test_dashboard_playground_feedback_to_queue(monkeypatch):
    state = {"pending": 0}
    monkeypatch.setenv("ITALIX_OPERATOR_TOKEN", "test-operator-token-0123456789abcde")

    def response(request, payload, status=200):
        return httpx.Response(status, json=payload, request=request)

    def fake_request(method, url, **kwargs):
        request = httpx.Request(method, url)
        path = request.url.path
        if path.startswith("/v1/"):
            assert kwargs["headers"]["Authorization"] == (
                "Bearer test-operator-token-0123456789abcde"
            )
        if path == "/health":
            return response(request, {"status": "ok", "local_model": "qwen-base"})
        if path == "/v1/dashboard/overview":
            return response(
                request,
                {
                    "total_requests": 1, "local_requests": 1, "cloud_requests": 0,
                    "captured_interactions": 1, "reviewed_interactions": 0,
                    "prompt_tokens": 10, "completion_tokens": 10,
                    "queue_pending": state["pending"], "training_jobs_completed": 1,
                    "active_models": [{"id": "qwen-base", "workload": "pr_summary"}],
                    "measured_cloud_cost_usd": None,
                    "cloud_cost_note": "No billing evidence.",
                },
            )
        if path == "/v1/traces" and method == "GET":
            return response(request, {"data": []})
        if path == "/v1/traces/trace_ui":
            return response(request, {"latency_ms": 123.0})
        if path == "/v1/traces/trace_ui/feedback":
            state["pending"] = 1
            return response(request, {"feedback_status": "approved", "queued": True})
        if path == "/v1/chat/completions":
            return response(
                request,
                {
                    "choices": [{"message": {"content": "## Summary\nApproved UI output"}}],
                    "italix": {
                        "trace_id": "trace_ui", "route": "local",
                        "registry_model": "qwen-base", "routing_reason": "active base",
                        "capture_enabled": True,
                    },
                },
            )
        if path == "/v1/training/queue":
            return response(request, {"pending": state["pending"], "counts": {"pending": state["pending"]}})
        if path == "/v1/training/jobs":
            return response(request, {"data": []})
        if path == "/v1/training/config":
            return response(request, {"engine": "MLX-LM", "rank": 4})
        if path == "/v1/models":
            return response(
                request,
                {"data": [
                    {"id": "qwen-base", "workload": "pr_summary", "kind": "base", "status": "base", "active": 1, "metrics_json": "{}"},
                    {"id": "qwen-base-triage", "workload": "change_triage", "kind": "base", "status": "base", "active": 1, "metrics_json": "{}"},
                ]},
            )
        if path in {"/v1/routes/pr_summary", "/v1/routes/change_triage"}:
            return response(request, {"id": "qwen-base-triage" if path.endswith("change_triage") else "qwen-base", "status": "base"})
        if path in {"/v1/routes/pr_summary/history", "/v1/routes/change_triage/history"}:
            return response(request, {"data": []})
        raise AssertionError(f"unexpected dashboard request: {method} {path}")

    monkeypatch.setattr(httpx, "request", fake_request)
    app = AppTest.from_file(str(Path(__file__).parents[1] / "dashboard.py"), default_timeout=20)
    app.run()
    assert not app.exception
    assert len(app.tabs) == 8

    next(area for area in app.text_area if area.label == "Developer request or Git diff").set_value(
        "Summarize this PR:\n\ndiff --git a/a.py b/a.py\n+x = 1"
    )
    next(button for button in app.button if button.label == "Run through ITALIX").click()
    app.run()
    assert not app.exception
    assert any(metric.label == "Route" and metric.value == "local" for metric in app.metric)

    next(button for button in app.button if button.label == "Approve response").click()
    app.run()
    assert not app.exception
    assert state["pending"] == 1
    assert any("Pending training examples: 1" in success.value for success in app.success)
