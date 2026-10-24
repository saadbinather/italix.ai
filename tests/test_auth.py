from __future__ import annotations

from fastapi.testclient import TestClient

from italix.api import create_app


VIEWER_TOKEN = "test-viewer-token-0123456789abcdef"
OPERATOR_TOKEN = "test-operator-token-0123456789abcde"
VIEWER = {"Authorization": f"Bearer {VIEWER_TOKEN}"}
OPERATOR = {"Authorization": f"Bearer {OPERATOR_TOKEN}"}


def make_client(tmp_path):
    app = create_app(
        database_path=tmp_path / "auth.db",
        viewer_token=VIEWER_TOKEN,
        operator_token=OPERATOR_TOKEN,
    )
    return TestClient(app)


def test_health_is_public_but_v1_requires_valid_bearer_token(tmp_path):
    client = make_client(tmp_path)
    assert client.get("/health").status_code == 200

    missing = client.get("/v1/dashboard/overview")
    assert missing.status_code == 401
    assert missing.headers["www-authenticate"] == "Bearer"

    invalid = client.get(
        "/v1/dashboard/overview", headers={"Authorization": "Bearer wrong-token"}
    )
    assert invalid.status_code == 401
    assert "wrong-token" not in invalid.text


def test_viewer_can_read_metrics_and_registry_only(tmp_path):
    client = make_client(tmp_path)
    for path in (
        "/v1/dashboard/overview",
        "/v1/models",
        "/v1/routes/pr_summary",
        "/v1/routes/pr_summary/history",
    ):
        assert client.get(path, headers=VIEWER).status_code == 200

    restricted = (
        ("GET", "/v1/traces"),
        ("GET", "/v1/training/queue"),
        ("GET", "/v1/memory/search?q=test"),
        ("POST", "/v1/chat/completions"),
        ("POST", "/v1/routes/pr_summary/rollback"),
    )
    for method, path in restricted:
        response = client.request(method, path, headers=VIEWER, json={} if method == "POST" else None)
        assert response.status_code == 403, (method, path, response.text)


def test_operator_can_access_sensitive_reads(tmp_path):
    client = make_client(tmp_path)
    assert client.get("/v1/traces", headers=OPERATOR).status_code == 200
    assert client.get("/v1/training/queue", headers=OPERATOR).status_code == 200
    assert client.get("/v1/memory/search?q=missing", headers=OPERATOR).status_code == 200


def test_equal_role_tokens_are_rejected(tmp_path):
    try:
        create_app(
            database_path=tmp_path / "equal.db",
            viewer_token="same-token-0123456789abcdefghijkl",
            operator_token="same-token-0123456789abcdefghijkl",
        )
    except RuntimeError as exc:
        assert "must be different" in str(exc)
    else:
        raise AssertionError("equal viewer/operator tokens must fail closed")
