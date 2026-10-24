"""Small, local-only MCP facade for the existing ITALIX FastAPI gateway."""

from __future__ import annotations

import json
import os
import re
import time
from typing import Annotated, Any, Literal

import httpx
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field


DEFAULT_API_URL = "http://127.0.0.1:8000"
DEFAULT_TIMEOUT_SECONDS = 180.0
SUPPORTED_WORKLOADS = ("pr_summary", "change_triage")
TRAINING_CONFIRMATION = "I confirm local LoRA training"
DEPLOYMENT_CONFIRMATION = "I confirm specialist activation"

# These patterns intentionally favor false positives over returning credentials
# to an MCP client. They cover the providers configured by ITALIX plus common
# authorization and environment-variable forms.
_SECRET_PATTERNS = (
    re.compile(
        r"(?i)(?:\b[A-Z][A-Z0-9_]*_)?(?:api[_-]?key|token|secret|password)\s*[:=]\s*[^\s,;]+"
    ),
    re.compile(r"(?i)\bbearer\s+[a-z0-9._~+/=-]+"),
    re.compile(r"\b(?:sk-|gsk_)[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{20,}\b"),
)


load_dotenv(override=False)


def _redact(value: str) -> str:
    result = value
    for pattern in _SECRET_PATTERNS:
        result = pattern.sub("[REDACTED]", result)
    return result


def _contains_secret(value: str) -> bool:
    return any(pattern.search(value) for pattern in _SECRET_PATTERNS)


def _evaluation_summary(evaluation: Any) -> Any:
    if not isinstance(evaluation, dict):
        return evaluation
    return {
        key: evaluation.get(key)
        for key in ("split", "qualified", "qualification_reason")
        if key in evaluation
    } | {
        "candidates": [
            {key: candidate.get(key) for key in ("name", "passed", "total")}
            for candidate in evaluation.get("candidates", [])
            if isinstance(candidate, dict)
        ]
    }


def _safe_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
        detail = payload.get("detail", "") if isinstance(payload, dict) else ""
    except ValueError:
        detail = ""
    if not isinstance(detail, str) or not detail.strip():
        detail = f"HTTP {response.status_code}"
    return _redact(detail)[:500]


class ItalixBackend:
    """Bounded HTTP access to the already-running local FastAPI process."""

    def __init__(
        self,
        base_url: str | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        token: str | None = None,
    ):
        self.base_url = (base_url or os.getenv("ITALIX_API_URL", DEFAULT_API_URL)).rstrip("/")
        self.timeout = timeout
        self.token = token or os.getenv("ITALIX_OPERATOR_TOKEN", "")

    async def request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        if path.startswith("/v1/"):
            if not self.token:
                raise ToolError("ITALIX operator authentication is not configured.")
            headers = dict(kwargs.pop("headers", {}) or {})
            headers["Authorization"] = f"Bearer {self.token}"
            kwargs["headers"] = headers
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.request(method, f"{self.base_url}{path}", **kwargs)
            response.raise_for_status()
            return response
        except httpx.TimeoutException as exc:
            raise ToolError("ITALIX backend timed out while processing the request.") from exc
        except httpx.ConnectError as exc:
            raise ToolError(
                "ITALIX backend is unavailable at 127.0.0.1:8000. Start FastAPI and retry."
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise ToolError(f"ITALIX backend rejected the request: {_safe_detail(exc.response)}") from exc
        except httpx.HTTPError as exc:
            raise ToolError("ITALIX backend request failed.") from exc


backend = ItalixBackend()
mcp = FastMCP(
    "ITALIX.ai",
    instructions=(
        "Local tools for the ITALIX AI optimization gateway. Chat calls never authorize "
        "cloud inference. Capture and feedback require explicit developer consent."
    ),
)


@mcp.tool(
    annotations=ToolAnnotations(
        title="Check ITALIX status",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
    structured_output=True,
)
async def italix_status() -> dict[str, Any]:
    """Check FastAPI health and active routes for supported ITALIX workloads."""
    health = (await backend.request("GET", "/health")).json()
    routes: dict[str, Any] = {}
    for workload in SUPPORTED_WORKLOADS:
        try:
            route = (await backend.request("GET", f"/v1/routes/{workload}")).json()
            routes[workload] = {
                "model": route.get("id"),
                "status": route.get("status"),
                "adapter_version": route.get("adapter_version"),
            }
        except ToolError as exc:
            routes[workload] = {"error": _redact(str(exc))[:500]}

    return {
        "status": health.get("status", "unknown"),
        "local_model": health.get("local_model"),
        "cloud_calls_require_request_opt_in": bool(
            health.get("cloud_calls_require_request_opt_in", True)
        ),
        "routes": routes,
    }


@mcp.tool(
    annotations=ToolAnnotations(
        title="Check ITALIX learning progress",
        readOnlyHint=True,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=False,
    ),
    structured_output=True,
)
async def italix_learning_status() -> dict[str, Any]:
    """Show local feedback queues, training jobs, adapters, routes, and evaluation progress."""
    queues = {}
    for workload in SUPPORTED_WORKLOADS:
        queues[workload] = (
            await backend.request("GET", "/v1/training/queue", params={"workload": workload})
        ).json()

    jobs_body = (await backend.request("GET", "/v1/training/jobs", params={"limit": 200})).json()
    models_body = (await backend.request("GET", "/v1/models")).json()
    overview = (await backend.request("GET", "/v1/dashboard/overview")).json()
    jobs = jobs_body.get("data", []) if isinstance(jobs_body, dict) else []
    models = models_body.get("data", []) if isinstance(models_body, dict) else []

    return {
        "workloads": queues,
        "training_jobs": [
            {
                key: job.get(key)
                for key in (
                    "id", "workload", "status", "example_count", "candidate_id",
                    "created_at", "completed_at",
                )
            }
            for job in jobs
            if job.get("status") in {"planned", "completed"}
        ],
        "adapters": [
            {
                "id": model.get("id"),
                "workload": model.get("workload"),
                "status": model.get("status"),
                "qualified": model.get("status") == "qualified",
                "active": bool(model.get("active")),
            }
            for model in models
            if model.get("kind") == "adapter"
        ],
        "active_models": [
            {
                "id": model.get("id"),
                "workload": model.get("workload"),
                "kind": model.get("kind"),
                "status": model.get("status"),
            }
            for model in models
            if model.get("active")
        ],
        "latest_evaluation": overview.get("latest_evaluation"),
    }


@mcp.tool(
    annotations=ToolAnnotations(
        title="Plan or train an ITALIX specialist",
        readOnlyHint=False,
        destructiveHint=True,
        idempotentHint=False,
        openWorldHint=False,
    ),
    structured_output=True,
)
async def italix_train_specialist(
    workload: Literal["pr_summary", "change_triage"],
    execute: bool = False,
    confirmation: str | None = None,
) -> dict[str, Any]:
    """Plan local LoRA training, or execute only after exact explicit confirmation."""
    queue = (
        await backend.request("GET", "/v1/training/queue", params={"workload": workload})
    ).json()
    config = (
        await backend.request("GET", "/v1/training/config", params={"workload": workload})
    ).json()
    plan = {
        "phase": "plan",
        "workload": workload,
        "ready": bool(queue.get("enough_examples", False)),
        "eligible_examples": queue.get("pending", 0),
        "minimum_examples": queue.get("minimum_examples", 10),
        "model": config.get("base_model"),
        "configuration": config,
        "estimated_resources": config.get("estimated_resources"),
        "confirmation_required": True,
        "confirmation_text": TRAINING_CONFIRMATION,
    }
    if not execute:
        return plan
    if confirmation != TRAINING_CONFIRMATION:
        raise ToolError(
            f'Explicit confirmation is required. Use confirmation="{TRAINING_CONFIRMATION}".'
        )
    if not plan["ready"]:
        raise ToolError(
            f"Insufficient approved examples for {workload}: "
            f"{plan['eligible_examples']}/{plan['minimum_examples']}."
        )

    job = (
        await backend.request(
            "POST",
            "/v1/training/jobs",
            json={
                "workload": workload,
                "minimum_examples": plan["minimum_examples"],
                "execute": True,
            },
        )
    ).json()
    candidate_id = job.get("candidate_id")
    if job.get("status") != "completed" or not candidate_id:
        raise ToolError("ITALIX training did not produce a completed adapter candidate.")
    evaluation = (
        await backend.request(
            "POST",
            f"/v1/models/{candidate_id}/evaluation",
            json={"workload": workload, "split": "valid"},
        )
    ).json()
    metrics = job.get("metrics")
    if metrics is None and isinstance(job.get("metrics_json"), str):
        try:
            metrics = json.loads(job["metrics_json"])
        except json.JSONDecodeError:
            metrics = None
    return {
        "phase": "executed",
        "workload": workload,
        "job_id": job.get("id"),
        "status": job.get("status"),
        "adapter_version": candidate_id,
        "training_metrics": metrics,
        "evaluation": evaluation,
        "activated": False,
    }


@mcp.tool(
    annotations=ToolAnnotations(
        title="Plan or deploy an ITALIX specialist",
        readOnlyHint=False,
        destructiveHint=True,
        idempotentHint=False,
        openWorldHint=False,
    ),
    structured_output=True,
)
async def italix_deploy_specialist(
    candidate_model: Annotated[str, Field(min_length=1, max_length=128)],
    execute: bool = False,
    confirmation: str | None = None,
) -> dict[str, Any]:
    """Plan specialist deployment, or activate a qualified adapter after confirmation."""

    async def deployment_plan() -> tuple[dict[str, Any], dict[str, Any]]:
        models_body = (await backend.request("GET", "/v1/models")).json()
        models = models_body.get("data", []) if isinstance(models_body, dict) else []
        candidate = next((model for model in models if model.get("id") == candidate_model), None)
        if candidate is None:
            raise ToolError(f"ITALIX model not found: {candidate_model}.")
        workload = candidate.get("workload")
        current_route = (await backend.request("GET", f"/v1/routes/{workload}")).json()
        evaluation = candidate.get("metrics")
        if evaluation is None and isinstance(candidate.get("metrics_json"), str):
            try:
                evaluation = json.loads(candidate["metrics_json"])
            except json.JSONDecodeError:
                evaluation = None
        plan = {
            "phase": "plan",
            "candidate_model": candidate.get("id"),
            "workload": workload,
            "evaluation": _evaluation_summary(evaluation),
            "current_route": {
                "model": current_route.get("id"),
                "status": current_route.get("status"),
            },
            "qualification_status": candidate.get("status"),
            "qualified": candidate.get("status") == "qualified",
            "activatable": (
                candidate.get("kind") == "adapter" and candidate.get("status") == "qualified"
            ),
            "confirmation_required": True,
            "confirmation_text": DEPLOYMENT_CONFIRMATION,
        }
        return plan, candidate

    plan, candidate = await deployment_plan()
    if not execute:
        return plan
    if confirmation != DEPLOYMENT_CONFIRMATION:
        raise ToolError(
            f'Explicit confirmation is required. Use confirmation="{DEPLOYMENT_CONFIRMATION}".'
        )
    if candidate.get("kind") != "adapter":
        raise ToolError("Only specialist adapter models can be deployed with this tool.")
    if candidate.get("status") == "experimental_failed":
        raise ToolError("Adapter is experimental_failed and is not eligible for deployment.")
    if candidate.get("status") != "qualified":
        raise ToolError(
            f"Adapter status {candidate.get('status')} is not eligible for deployment."
        )

    activated = (
        await backend.request(
            "POST",
            f"/v1/models/{candidate_model}/activate",
            json={"workload": candidate["workload"]},
        )
    ).json()
    history_body = (
        await backend.request(
            "GET", f"/v1/routes/{candidate['workload']}/history", params={"limit": 1}
        )
    ).json()
    history = history_body.get("data", []) if isinstance(history_body, dict) else []
    return {
        "phase": "deployed",
        "candidate_model": candidate_model,
        "workload": candidate["workload"],
        "status": activated.get("status"),
        "active": bool(activated.get("active")),
        "evaluation": plan["evaluation"],
        "audit_event": history[0] if history else None,
    }


@mcp.tool(
    annotations=ToolAnnotations(
        title="Chat with local ITALIX",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    ),
    structured_output=True,
)
async def italix_chat(
    task: Annotated[
        str,
        Field(
            min_length=1,
            max_length=20_000,
            description="Developer task or Git diff to send to the local ITALIX gateway.",
        ),
    ],
    workload: Literal["pr_summary", "change_triage"] = "pr_summary",
    model: Literal["italix-auto", "pr-summary-deterministic-v1"] = "italix-auto",
    capture: Annotated[
        bool,
        Field(description="Capture the prompt and response locally for possible feedback. Set true only with explicit user consent."),
    ] = False,
) -> dict[str, Any]:
    """Run a developer task locally; capture only when the user explicitly consents."""
    task = task.strip()
    if not task:
        raise ToolError("Task must not be empty.")
    if _contains_secret(task):
        raise ToolError("Task appears to contain a credential or secret; remove it before retrying.")

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": task}],
        "max_tokens": 160,
        "temperature": 0.0,
        "stream": False,
        "workload": workload,
        "capture": capture,
        "allow_cloud": False,
    }
    started = time.perf_counter()
    response = await backend.request("POST", "/v1/chat/completions", json=payload)
    latency_ms = round((time.perf_counter() - started) * 1000, 2)
    body = response.json()

    try:
        answer = body["choices"][0]["message"]["content"]
        metadata = body["italix"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ToolError("ITALIX backend returned an invalid completion response.") from exc

    if not isinstance(answer, str):
        raise ToolError("ITALIX backend returned an invalid completion response.")
    result = {
        "answer": _redact(answer),
        "model": metadata.get("registry_model") or body.get("model"),
        "route": metadata.get("route"),
        "latency_ms": latency_ms,
        "trace_id": metadata.get("trace_id") or response.headers.get("x-italix-trace-id"),
        "capture_enabled": bool(metadata.get("capture_enabled", capture)),
        "abstained": bool(metadata.get("abstained", False)),
        "abstention_reasons": metadata.get("abstention_reasons", []),
        "adapter_used": bool(metadata.get("adapter_used", False)),
    }
    if model == "pr-summary-deterministic-v1":
        result["validation"] = metadata.get("deterministic_validation") or {
            "valid": False,
            "reason": "backend did not return deterministic PR validation",
        }
    if workload == "change_triage":
        result["validation"] = metadata.get("validation") or {
            "valid": False,
            "reason": "backend did not return change_triage validation",
        }
    return result


@mcp.tool(
    annotations=ToolAnnotations(
        title="Submit ITALIX developer feedback",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    ),
    structured_output=True,
)
async def italix_submit_feedback(
    trace_id: Annotated[str, Field(min_length=7, max_length=128)],
    action: Literal["approve", "correct", "reject"],
    corrected_response: str | dict[str, str] | None = None,
) -> dict[str, Any]:
    """Submit explicit developer feedback for a trace; never starts training."""
    trace_id = trace_id.strip()
    if isinstance(corrected_response, dict):
        corrected_response = json.dumps(corrected_response, separators=(",", ":"))
    if action == "correct" and not (corrected_response or "").strip():
        raise ToolError("corrected_response is required for correct feedback.")
    if corrected_response is not None and len(corrected_response) > 20_000:
        raise ToolError("corrected_response must be at most 20000 characters.")
    if action != "correct" and corrected_response is not None:
        raise ToolError("corrected_response is only valid with correct feedback.")
    if corrected_response and _contains_secret(corrected_response):
        raise ToolError("Correction appears to contain a credential or secret; remove it before retrying.")
    payload = {"action": action}
    if action == "correct":
        payload["corrected_response"] = corrected_response.strip()
    result = (
        await backend.request("POST", f"/v1/traces/{trace_id}/feedback", json=payload)
    ).json()
    return {
        "trace_id": result.get("trace_id", trace_id),
        "feedback_status": result.get("feedback_status"),
        "queued": bool(result.get("queued", False)),
    }


def main() -> None:
    """Run the MCP server on standard input/output for a local Codex client."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
