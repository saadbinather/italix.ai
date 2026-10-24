from __future__ import annotations

import os
import socket
import threading
import time
from contextlib import closing
from pathlib import Path

import anyio
import pytest
import uvicorn
from fastapi import FastAPI, HTTPException
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from italix import mcp_server
from italix.api import create_app
from italix.engines import Generation


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def fake_backend():
    app = FastAPI()
    observed: dict = {}

    @app.get("/health")
    def health():
        return {
            "status": "ok",
            "local_model": "qwen-base",
            "gemini_configured": True,
            "cloud_calls_require_request_opt_in": True,
        }

    @app.get("/v1/routes/{workload}")
    def route(workload: str):
        return {
            "id": "qwen-base-triage" if workload == "change_triage" else "qwen-base",
            "status": "base",
            "adapter_version": None,
        }

    @app.post("/v1/chat/completions")
    def chat(payload: dict):
        observed["chat"] = payload
        if payload["messages"][0]["content"] == "invalid":
            raise HTTPException(422, "Invalid developer task")
        deterministic = payload["model"] == "pr-summary-deterministic-v1"
        return {
            "model": "mlx-community/Qwen2.5-1.5B-Instruct-4bit",
            "choices": [{"message": {"content": "Local answer password=test-placeholder"}}],
            "italix": {
                "registry_model": "pr-summary-deterministic-v1" if deterministic else "qwen-base",
                "route": "deterministic" if deterministic else "local",
                "trace_id": "trace_mcp_test",
                "capture_enabled": payload["capture"],
                "abstained": deterministic,
                "abstention_reasons": ["synthetic abstention"] if deterministic else [],
                "adapter_used": False,
                "deterministic_validation": {"valid": True} if deterministic else None,
                "validation": (
                    {"valid": False, "reason": "synthetic invalid classification"}
                    if payload["workload"] == "change_triage" else None
                ),
            },
        }

    @app.post("/v1/traces/{trace_id}/feedback")
    def feedback(trace_id: str, payload: dict):
        observed["feedback"] = {"trace_id": trace_id, **payload}
        return {
            "trace_id": trace_id,
            "feedback_status": "corrected_approved",
            "queued": True,
        }

    @app.get("/v1/training/queue")
    def queue(workload: str):
        pending = 12 if workload == "pr_summary" else 3
        return {
            "workload": workload,
            "counts": {"pending": pending},
            "pending": pending,
            "minimum_examples": 10,
            "enough_examples": pending >= 10,
        }

    @app.get("/v1/training/jobs")
    def jobs(limit: int = 50):
        return {"data": [
            {"id": 2, "workload": "pr_summary", "status": "planned", "example_count": 12,
             "candidate_id": None, "created_at": "2026-10-20T00:00:00Z", "completed_at": None},
            {"id": 1, "workload": "pr_summary", "status": "completed", "example_count": 10,
             "candidate_id": "adapter-v3", "created_at": "2026-10-19T00:00:00Z",
             "completed_at": "2026-10-19T01:00:00Z"},
            {"id": 3, "workload": "change_triage", "status": "failed"},
        ]}

    @app.get("/v1/models")
    def models():
        return {"data": [
            {"id": "qwen-base", "workload": "pr_summary", "kind": "base", "status": "base", "active": 1},
            {"id": "adapter-v3", "workload": "pr_summary", "kind": "adapter", "status": "experimental_failed", "active": 0,
             "metrics_json": '{"qualified":false,"candidates":[{"name":"candidate","passed":4,"total":6}]}'},
            {"id": "adapter-qualified", "workload": "pr_summary", "kind": "adapter", "status": "qualified", "active": 0,
             "metrics_json": '{"qualified":true,"candidates":[{"name":"candidate","passed":6,"total":6}]}'},
            {"id": "qwen-base-triage", "workload": "change_triage", "kind": "base", "status": "base", "active": 1},
        ]}

    @app.get("/v1/dashboard/overview")
    def overview():
        return {"latest_evaluation": {"model_id": "adapter-v3", "qualified": False}}

    @app.get("/v1/training/config")
    def training_config(workload: str):
        return {
            "engine": "MLX-LM",
            "base_model": "mlx-community/Qwen2.5-1.5B-Instruct-4bit",
            "fine_tune_type": "LoRA",
            "workload": workload,
            "cloud_required": False,
            "estimated_resources": {
                "duration_seconds": "20-60",
                "peak_mlx_memory_gb": 2.0,
                "trainable_parameters": 659456,
            },
        }

    @app.post("/v1/training/jobs")
    def execute_training(payload: dict):
        observed["training"] = payload
        return {
            "id": 4,
            "workload": payload["workload"],
            "status": "completed",
            "candidate_id": "adapter-job-4",
            "metrics_json": '{"optimizer_steps":28,"changed_elements":659456}',
        }

    @app.post("/v1/models/{model_id}/evaluation")
    def evaluate(model_id: str, payload: dict):
        observed["evaluation"] = {"model_id": model_id, **payload}
        return {"id": model_id, "status": "qualified", "qualified": True,
                "evaluation": {"split": "valid", "qualified": True}}

    @app.post("/v1/models/{model_id}/activate")
    def activate(model_id: str, payload: dict):
        observed["activation"] = {"model_id": model_id, **payload}
        if model_id == "adapter-v3":
            raise HTTPException(409, "model status experimental_failed is not eligible for deployment")
        return {"id": model_id, "workload": payload["workload"], "kind": "adapter",
                "status": "qualified", "active": 1}

    @app.get("/v1/routes/{workload}/history")
    def history(workload: str, limit: int = 50):
        return {"data": [{"id": 7, "workload": workload, "model_id": "adapter-qualified",
                           "action": "activate", "created_at": "2026-10-20T00:00:00Z"}]}

    with closing(socket.socket()) as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 5
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.01)
    if not server.started:
        pytest.fail("test backend did not start")
    try:
        yield f"http://127.0.0.1:{port}", observed
    finally:
        server.should_exit = True
        thread.join(timeout=5)


def test_secret_detection_and_redaction():
    assert mcp_server._contains_secret("GEMINI_API_KEY=private-value")
    assert mcp_server._contains_secret("Bearer abcdefghijklmnop")
    assert not mcp_server._contains_secret("Summarize changes to api_key_validator.py")
    assert "private-value" not in mcp_server._redact("api_key=private-value")


def test_stdio_discovery_and_tools_with_actual_mcp_client(fake_backend):
    base_url, observed = fake_backend

    async def exercise():
        env = os.environ.copy()
        env["ITALIX_API_URL"] = base_url
        env["ITALIX_OPERATOR_TOKEN"] = "test-operator-token-0123456789abcde"
        parameters = StdioServerParameters(
            command=str(PROJECT_ROOT / ".venv/bin/python"),
            args=["-m", "italix.mcp_server"],
            cwd=str(PROJECT_ROOT),
            env=env,
        )
        async with stdio_client(parameters) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                initialized = await session.initialize()
                assert initialized.serverInfo.name == "ITALIX.ai"

                tools = await session.list_tools()
                assert [tool.name for tool in tools.tools] == [
                    "italix_status", "italix_learning_status", "italix_train_specialist",
                    "italix_deploy_specialist", "italix_chat", "italix_submit_feedback"
                ]
                chat_schema = next(tool for tool in tools.tools if tool.name == "italix_chat")
                assert chat_schema.inputSchema["properties"]["task"]["maxLength"] == 20_000
                assert chat_schema.inputSchema["properties"]["capture"]["default"] is False

                status = await session.call_tool("italix_status", {})
                assert status.isError is False
                assert status.structuredContent["routes"]["pr_summary"]["model"] == "qwen-base"

                learning = await session.call_tool("italix_learning_status", {})
                assert learning.isError is False
                assert learning.structuredContent["workloads"]["pr_summary"]["enough_examples"] is True
                assert learning.structuredContent["workloads"]["change_triage"]["enough_examples"] is False
                assert [job["status"] for job in learning.structuredContent["training_jobs"]] == ["planned", "completed"]
                assert learning.structuredContent["adapters"][0]["qualified"] is False
                assert len(learning.structuredContent["active_models"]) == 2
                assert learning.structuredContent["latest_evaluation"]["qualified"] is False

                plan = await session.call_tool(
                    "italix_train_specialist", {"workload": "pr_summary"}
                )
                assert plan.isError is False
                assert plan.structuredContent["phase"] == "plan"
                assert plan.structuredContent["ready"] is True
                assert plan.structuredContent["eligible_examples"] == 12
                assert plan.structuredContent["model"].endswith("Qwen2.5-1.5B-Instruct-4bit")
                assert "training" not in observed

                no_consent = await session.call_tool(
                    "italix_train_specialist",
                    {"workload": "pr_summary", "execute": True},
                )
                assert no_consent.isError is True
                assert "Explicit confirmation" in no_consent.content[0].text
                assert "training" not in observed

                insufficient = await session.call_tool(
                    "italix_train_specialist",
                    {
                        "workload": "change_triage",
                        "execute": True,
                        "confirmation": "I confirm local LoRA training",
                    },
                )
                assert insufficient.isError is True
                assert "3/10" in insufficient.content[0].text
                assert "training" not in observed

                executed = await session.call_tool(
                    "italix_train_specialist",
                    {
                        "workload": "pr_summary",
                        "execute": True,
                        "confirmation": "I confirm local LoRA training",
                    },
                )
                assert executed.isError is False
                assert executed.structuredContent["job_id"] == 4
                assert executed.structuredContent["adapter_version"] == "adapter-job-4"
                assert executed.structuredContent["training_metrics"]["optimizer_steps"] == 28
                assert executed.structuredContent["evaluation"]["qualified"] is True
                assert executed.structuredContent["activated"] is False

                deploy_plan = await session.call_tool(
                    "italix_deploy_specialist", {"candidate_model": "adapter-qualified"}
                )
                assert deploy_plan.isError is False
                assert deploy_plan.structuredContent["phase"] == "plan"
                assert deploy_plan.structuredContent["current_route"]["model"] == "qwen-base"
                assert deploy_plan.structuredContent["qualified"] is True
                assert deploy_plan.structuredContent["activatable"] is True
                assert "activation" not in observed

                deploy_no_consent = await session.call_tool(
                    "italix_deploy_specialist",
                    {"candidate_model": "adapter-qualified", "execute": True},
                )
                assert deploy_no_consent.isError is True
                assert "Explicit confirmation" in deploy_no_consent.content[0].text
                assert "activation" not in observed

                failed_deploy = await session.call_tool(
                    "italix_deploy_specialist",
                    {"candidate_model": "adapter-v3", "execute": True,
                     "confirmation": "I confirm specialist activation"},
                )
                assert failed_deploy.isError is True
                assert "experimental_failed" in failed_deploy.content[0].text
                assert "activation" not in observed

                deployed = await session.call_tool(
                    "italix_deploy_specialist",
                    {"candidate_model": "adapter-qualified", "execute": True,
                     "confirmation": "I confirm specialist activation"},
                )
                assert deployed.isError is False
                assert deployed.structuredContent["phase"] == "deployed"
                assert deployed.structuredContent["active"] is True
                assert deployed.structuredContent["audit_event"]["action"] == "activate"

                chat = await session.call_tool(
                    "italix_chat",
                    {"task": "Summarize this change", "workload": "pr_summary", "capture": True},
                )
                assert chat.isError is False
                assert chat.structuredContent["model"] == "qwen-base"
                assert chat.structuredContent["route"] == "local"
                assert chat.structuredContent["trace_id"] == "trace_mcp_test"
                assert chat.structuredContent["answer"] == "Local answer [REDACTED]"
                assert chat.structuredContent["latency_ms"] >= 0
                assert chat.structuredContent["capture_enabled"] is True

                deterministic = await session.call_tool(
                    "italix_chat",
                    {"task": "diff --git a/a.py b/a.py", "workload": "pr_summary",
                     "model": "pr-summary-deterministic-v1"},
                )
                assert deterministic.isError is False
                assert deterministic.structuredContent["model"] == "pr-summary-deterministic-v1"
                assert deterministic.structuredContent["route"] == "deterministic"
                assert deterministic.structuredContent["abstained"] is True
                assert deterministic.structuredContent["validation"]["valid"] is True
                assert deterministic.structuredContent["adapter_used"] is False

                triage = await session.call_tool(
                    "italix_chat", {"task": "diff --git a/auth/permissions/a.py b/auth/permissions/a.py", "workload": "change_triage"}
                )
                assert triage.structuredContent["validation"]["valid"] is False

                feedback = await session.call_tool(
                    "italix_submit_feedback",
                    {
                        "trace_id": "trace_mcp_test",
                        "action": "correct",
                        "corrected_response": '{"owner":"identity","risk":"high","reviewer":"security"}',
                    },
                )
                assert feedback.isError is False
                assert feedback.structuredContent["queued"] is True

                secret = await session.call_tool(
                    "italix_chat", {"task": "GEMINI_API_KEY=private-value"}
                )
                assert secret.isError is True
                assert "private-value" not in secret.content[0].text

                invalid = await session.call_tool("italix_chat", {"task": "invalid"})
                assert invalid.isError is True
                assert "Invalid developer task" in invalid.content[0].text

        assert observed["chat"]["allow_cloud"] is False
        assert observed["chat"]["capture"] is False
        assert observed["chat"]["model"] == "italix-auto"
        assert observed["feedback"]["action"] == "correct"
        assert observed["training"] == {
            "workload": "pr_summary", "minimum_examples": 10, "execute": True
        }
        assert observed["evaluation"]["model_id"] == "adapter-job-4"
        assert observed["activation"] == {
            "model_id": "adapter-qualified", "workload": "pr_summary"
        }

    anyio.run(exercise)


def test_real_authenticated_mcp_calls_actual_gateway(tmp_path):
    class LocalEngine:
        configured = True

        def generate(self, messages, max_tokens, temperature, adapter_path=None):
            return Generation("Authenticated local response", "test-local", 4, 3)

    app = create_app(
        database_path=tmp_path / "authenticated-mcp.db",
        local_engine=LocalEngine(),
        viewer_token="mcp-viewer-token-0123456789abcdefg",
        operator_token="mcp-operator-token-0123456789abcdef",
    )
    with closing(socket.socket()) as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 5
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.01)
    assert server.started

    async def exercise():
        env = os.environ.copy()
        env["ITALIX_API_URL"] = f"http://127.0.0.1:{port}"
        env["ITALIX_OPERATOR_TOKEN"] = "mcp-operator-token-0123456789abcdef"
        parameters = StdioServerParameters(
            command=str(PROJECT_ROOT / ".venv/bin/python"),
            args=["-m", "italix.mcp_server"],
            cwd=str(PROJECT_ROOT),
            env=env,
        )
        async with stdio_client(parameters) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                status = await session.call_tool("italix_status", {})
                assert status.isError is False
                assert status.structuredContent["routes"]["pr_summary"]["model"] == "qwen-base"
                chat = await session.call_tool(
                    "italix_chat", {"task": "Summarize a harmless synthetic change"}
                )
                assert chat.isError is False
                assert chat.structuredContent["answer"] == "Authenticated local response"
                assert chat.structuredContent["route"] == "local"

    try:
        anyio.run(exercise)
    finally:
        server.should_exit = True
        thread.join(timeout=5)


def test_backend_unavailable_is_safe(monkeypatch):
    async def exercise():
        monkeypatch.setattr(
            mcp_server,
            "backend",
            mcp_server.ItalixBackend("http://127.0.0.1:1", timeout=0.1),
        )
        with pytest.raises(Exception, match="backend is unavailable") as error:
            await mcp_server.italix_status()
        assert "API_KEY" not in str(error.value)

    anyio.run(exercise)


def test_backend_timeout_is_safe(monkeypatch):
    class TimeoutClient:
        async def request(self, method, path, **kwargs):
            raise mcp_server.ToolError("ITALIX backend timed out while processing the request.")

    async def exercise():
        monkeypatch.setattr(mcp_server, "backend", TimeoutClient())
        with pytest.raises(Exception, match="timed out"):
            await mcp_server.italix_chat("Summarize this PR")

    anyio.run(exercise)


def test_feedback_arguments_are_bounded(monkeypatch):
    class UnexpectedBackend:
        async def request(self, method, path, **kwargs):
            raise AssertionError("backend must not be called")

    async def exercise():
        monkeypatch.setattr(mcp_server, "backend", UnexpectedBackend())
        with pytest.raises(Exception, match="required"):
            await mcp_server.italix_submit_feedback("trace_1", "correct")
        with pytest.raises(Exception, match="only valid"):
            await mcp_server.italix_submit_feedback("trace_1", "approve", "unexpected")

    anyio.run(exercise)
