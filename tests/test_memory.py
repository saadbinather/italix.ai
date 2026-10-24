from __future__ import annotations

import json
import subprocess

from fastapi.testclient import TestClient

from italix.api import create_app
from italix.engines import Generation


OPERATOR_HEADERS = {"Authorization": "Bearer test-operator-token-0123456789abcde"}


class MemoryEngine:
    configured = False
    model = "fake-local"

    def __init__(self):
        self.calls = 0

    def generate(self, messages, max_tokens, temperature, adapter_path=None):
        self.calls += 1
        assert adapter_path is None
        assert "Evidence:" in messages[-1]["content"]
        return Generation(
            "The plan catalog was cached to reduce repeated database reads. This is recorded evidence.",
            "fake-local",
            20,
            15,
        )


def git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    ).stdout


def make_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q")
    git(repo, "config", "user.name", "Demo Team")
    git(repo, "config", "user.email", "demo@example.invalid")
    decision = repo / "decision.md"
    decision.write_text("Redis caches plan catalog reads for 60 seconds with PostgreSQL fallback.\n")
    git(repo, "add", "decision.md")
    git(repo, "commit", "-q", "-m", "Add Redis plan cache with database fallback")
    return repo


def make_client(tmp_path):
    engine = MemoryEngine()
    app = create_app(
        database_path=tmp_path / "italix.db",
        local_engine=engine,
        gemini_engine=MemoryEngine(),
        groq_engine=MemoryEngine(),
    )
    return TestClient(app, headers=OPERATOR_HEADERS), engine


def test_git_and_discussion_import_search_query_and_deduplication(tmp_path):
    client, engine = make_client(tmp_path)
    repo = make_repo(tmp_path)
    imported = client.post(
        "/v1/memory/import/git",
        json={"repository_path": str(repo), "max_commits": 10, "include_diff_summary": True},
    )
    assert imported.status_code == 200
    assert imported.json()["imported"] == 1
    assert imported.json()["code_executed"] is False
    duplicate = client.post(
        "/v1/memory/import/git", json={"repository_path": str(repo), "max_commits": 10}
    )
    assert duplicate.json()["duplicates"] == 1

    discussions = tmp_path / "approved.jsonl"
    discussions.write_text(
        json.dumps(
            {
                "message_id": "msg-redis", "channel": "architecture",
                "timestamp": "2026-02-03T14:05:00Z", "author": "SRE",
                "text": "Redis reduces duplicate plan catalog reads; PostgreSQL remains the source of truth.",
                "thread_id": "thread-redis", "permalink": "https://example.invalid/msg-redis",
            }
        ) + "\n"
    )
    discussion_import = client.post(
        "/v1/memory/import/discussions", json={"file_path": str(discussions)}
    )
    assert discussion_import.json()["imported"] == 1

    results = client.get("/v1/memory/search", params={"q": "Why Redis plan caching?"}).json()["data"]
    assert {item["kind"] for item in results} == {"git", "discussion"}
    source = client.get(f"/v1/memory/sources/{results[0]['id']}")
    assert source.status_code == 200
    answer = client.post(
        "/v1/memory/query", json={"question": "Why did we introduce Redis caching?"}
    ).json()
    assert answer["abstained"] is False
    assert answer["cloud_used"] is False
    assert answer["sources"]
    assert "Sources:" in answer["answer"]
    assert engine.calls == 1

    with app_database(client).connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM training_queue").fetchone()[0] == 0


def app_database(client):
    return client.app.state.database


def test_memory_abstains_without_evidence_and_does_not_call_model(tmp_path):
    client, engine = make_client(tmp_path)
    answer = client.post(
        "/v1/memory/query", json={"question": "Why did we select a lunar database?"}
    ).json()
    assert answer["abstained"] is True
    assert answer["sources"] == []
    assert engine.calls == 0


def test_git_import_rejects_non_repository(tmp_path):
    client, _ = make_client(tmp_path)
    response = client.post(
        "/v1/memory/import/git", json={"repository_path": str(tmp_path)}
    )
    assert response.status_code == 400
