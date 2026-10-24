from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from italix.api import create_app
from italix.database import utc_now


VIEWER = {"Authorization": "Bearer overview-viewer-token-0123456789abc"}
OPERATOR = {"Authorization": "Bearer overview-operator-token-0123456789ab"}


def make_overview_client(tmp_path):
    app = create_app(
        database_path=tmp_path / "overview.db",
        viewer_token=VIEWER["Authorization"].removeprefix("Bearer "),
        operator_token=OPERATOR["Authorization"].removeprefix("Bearer "),
    )
    return TestClient(app), app


def insert_trace(database, trace_id, route, latency, *, error=None, prompt=2, completion=3):
    database.insert_trace(
        {
            "id": trace_id,
            "created_at": utc_now(),
            "workload": "pr_summary",
            "requested_model": "italix-auto",
            "selected_model": "synthetic-model",
            "route": route,
            "routing_reason": "overview regression test",
            "capture_enabled": 0,
            "prompt_json": None,
            "response_text": None,
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "latency_ms": latency,
            "validation_json": json.dumps({}),
            "feedback_status": "pending",
            "error": error,
        }
    )


def test_empty_overview_is_typed_and_zero_safe(tmp_path):
    client, _ = make_overview_client(tmp_path)
    response = client.get("/v1/dashboard/overview", headers=VIEWER)
    assert response.status_code == 200
    overview = response.json()
    assert overview["total_requests"] == 0
    assert overview["successful_requests"] == 0
    assert overview["local_requests"] == 0
    assert overview["deterministic_requests"] == 0
    assert overview["model_inference_requests"] == 0
    assert overview["cloud_requests"] == 0
    assert overview["average_local_latency_ms"] is None
    assert overview["latency"]["average_deterministic_latency_ms"] is None
    assert overview["costs"] == {
        "measured_cloud_cost_usd": None,
        "projected_cost_usd": None,
        "projection_configured": False,
        "note": "No provider billing or price evidence has been recorded.",
    }
    assert overview["registry"]["base_models"] == 2
    assert overview["registry"]["deterministic_systems"] == 1
    assert overview["registry"]["experimental_lora_adapters"] == 2

    schema = client.get("/openapi.json").json()["paths"]["/v1/dashboard/overview"][
        "get"
    ]["responses"]["200"]["content"]["application/json"]["schema"]
    assert schema["$ref"].endswith("/DashboardOverviewResponse")


def test_mixed_routes_have_distinct_counts_and_accurate_latency(tmp_path):
    client, app = make_overview_client(tmp_path)
    insert_trace(app.state.database, "det-ok", "deterministic", 10.0)
    insert_trace(app.state.database, "det-failed", "deterministic", 999.0, error="failed")
    insert_trace(app.state.database, "model-ok", "local", 30.0)
    insert_trace(app.state.database, "cloud-ok", "cloud", 50.0)
    insert_trace(app.state.database, "other-ok", "abstain", 5.0)

    overview = client.get("/v1/dashboard/overview", headers=VIEWER).json()
    usage = overview["observed_usage"]
    assert usage == {
        "total_requests": 5,
        "successful_requests": 4,
        "failed_requests": 1,
        "local_requests": 3,
        "deterministic_requests": 2,
        "model_inference_requests": 1,
        "cloud_requests": 1,
        "other_requests": 1,
        "captured_interactions": 0,
        "reviewed_interactions": 0,
        "prompt_tokens": 10,
        "completion_tokens": 15,
    }
    assert overview["average_local_latency_ms"] == pytest.approx(20.0)
    assert overview["average_deterministic_latency_ms"] == pytest.approx(10.0)
    assert overview["average_model_inference_latency_ms"] == pytest.approx(30.0)
    assert overview["average_cloud_latency_ms"] == pytest.approx(50.0)


def test_viewer_overview_exposes_only_aggregate_non_sensitive_data(tmp_path):
    client, app = make_overview_client(tmp_path)
    insert_trace(app.state.database, "private-trace-id", "local", 12.0)
    response = client.get("/v1/dashboard/overview", headers=VIEWER)
    assert response.status_code == 200
    serialized = response.text.lower()
    for forbidden in ("private-trace-id", "prompt_json", "response_text", "routing_reason"):
        assert forbidden not in serialized
    assert client.get("/v1/traces", headers=VIEWER).status_code == 403
    assert client.get("/v1/dashboard/overview").status_code == 401
