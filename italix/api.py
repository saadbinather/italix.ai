"""FastAPI application factory for the ITALIX.ai core platform."""

from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Response

from italix.auth import BearerAuthorizer
from italix.database import Database
from italix.engines import (
    DeterministicPRSummaryEngine,
    GeminiEngine,
    GroqEngine,
    LocalMLXEngine,
)
from italix.evaluation import ServerEvaluator
from italix.memory import MemoryService
from italix.change_triage import PRODUCTION_PROMPT, deterministic_triage
from italix.schemas import (
    ActivationRequest,
    DashboardOverviewResponse,
    ChatCompletionRequest,
    FeedbackRequest,
    GitMemoryImportRequest,
    DiscussionMemoryImportRequest,
    MemoryQueryRequest,
    HybridTriageRequest,
    ModelEvaluationRequest,
    TrainingJobRequest,
)
from italix.service import GatewayService
from italix.training_jobs import TrainingJobRunner


def create_app(
    *,
    database_path: str | Path | None = None,
    local_engine=None,
    gemini_engine=None,
    groq_engine=None,
    training_runner=None,
    evaluation_runner=None,
    deterministic_pr_engine=None,
    viewer_token: str | None = None,
    operator_token: str | None = None,
) -> FastAPI:
    load_dotenv(override=False)
    database = Database(database_path or os.getenv("ITALIX_DB_PATH", "var/italix.db"))
    database.initialize()
    service = GatewayService(
        database=database,
        local=local_engine or LocalMLXEngine(),
        gemini=gemini_engine or GeminiEngine(),
        groq=groq_engine or GroqEngine(),
        deterministic_pr=deterministic_pr_engine or DeterministicPRSummaryEngine(),
    )
    runner = training_runner or TrainingJobRunner(database)
    evaluator = evaluation_runner or ServerEvaluator()
    memory = MemoryService(database, service.local)
    authorizer = BearerAuthorizer.from_environment(viewer_token, operator_token)
    app = FastAPI(title="ITALIX.ai", version="0.8.0")
    app.state.database = database
    app.state.gateway = service
    app.state.training_runner = runner
    app.state.evaluation_runner = evaluator
    app.state.memory = memory

    @app.get("/health")
    def health():
        return {
            "status": "ok",
            "local_model": "qwen-base",
            "gemini_configured": bool(getattr(service.gemini, "configured", False)),
            "groq_configured": bool(getattr(service.groq, "configured", False)),
            "cloud_calls_require_request_opt_in": True,
        }

    @app.post("/v1/chat/completions", dependencies=[Depends(authorizer.require_operator)])
    def chat_completion(request: ChatCompletionRequest, response: Response):
        try:
            body, trace_id = service.complete(request)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        response.headers["x-italix-trace-id"] = trace_id
        return body

    @app.get("/v1/traces/{trace_id}", dependencies=[Depends(authorizer.require_operator)])
    def get_trace(trace_id: str):
        trace = database.trace(trace_id)
        if trace is None:
            raise HTTPException(status_code=404, detail="trace not found")
        for field in ("prompt_json", "validation_json"):
            if trace[field] is not None:
                trace[field.removesuffix("_json")] = json.loads(trace.pop(field))
        return trace

    @app.get(
        "/v1/dashboard/overview",
        dependencies=[Depends(authorizer.require_viewer)],
        response_model=DashboardOverviewResponse,
    )
    def dashboard_overview():
        return database.dashboard_overview()

    @app.get("/v1/traces", dependencies=[Depends(authorizer.require_operator)])
    def traces(limit: int = 50):
        return {"data": database.list_trace_metadata(max(1, min(limit, 200)))}

    @app.post(
        "/v1/traces/{trace_id}/feedback",
        dependencies=[Depends(authorizer.require_operator)],
    )
    def feedback(trace_id: str, request: FeedbackRequest):
        try:
            return database.add_feedback(trace_id, request.action, request.corrected_response)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail="trace not found") from exc
        except PermissionError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/v1/training/queue", dependencies=[Depends(authorizer.require_operator)])
    def training_queue(workload: str | None = None, minimum_examples: int = 10):
        if minimum_examples < 1:
            raise HTTPException(status_code=422, detail="minimum_examples must be at least 1")
        return database.queue_summary(workload, minimum_examples)

    @app.post(
        "/v1/training/jobs",
        status_code=202,
        dependencies=[Depends(authorizer.require_operator)],
    )
    def plan_training(request: TrainingJobRequest):
        try:
            planned = database.create_training_job(
                request.workload, request.minimum_examples, request.candidate_id
            )
            if not request.execute:
                return planned
            candidate_id = request.candidate_id or f"adapter-job-{planned['id']}"
            return runner.execute(planned["id"], candidate_id)
        except PermissionError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except (RuntimeError, ValueError) as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.get("/v1/training/jobs", dependencies=[Depends(authorizer.require_operator)])
    def training_jobs(limit: int = 50):
        return {"data": database.list_training_jobs(max(1, min(limit, 200)))}

    @app.get("/v1/training/config", dependencies=[Depends(authorizer.require_operator)])
    def training_config(workload: str = "pr_summary"):
        try:
            return runner.public_config(workload)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/v1/models", dependencies=[Depends(authorizer.require_viewer)])
    def models():
        return {"data": database.list_models()}

    @app.post(
        "/v1/models/{model_id}/activate",
        dependencies=[Depends(authorizer.require_operator)],
    )
    def activate(model_id: str, request: ActivationRequest):
        try:
            return database.activate_model(model_id, request.workload)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail="model not found") from exc
        except PermissionError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post(
        "/v1/models/{model_id}/evaluation",
        dependencies=[Depends(authorizer.require_operator)],
    )
    def record_evaluation(model_id: str, request: ModelEvaluationRequest):
        models = {model["id"]: model for model in database.list_models()}
        if model_id not in models:
            raise HTTPException(status_code=404, detail="model not found")
        model = models[model_id]
        if model["workload"] != request.workload:
            raise HTTPException(status_code=409, detail="workload does not match model")
        try:
            result = evaluator.compare(model["path"], split=request.split, workload=model["workload"])
            return database.apply_model_evaluation(model_id, result)
        except PermissionError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post(
        "/v1/routes/{workload}/rollback",
        dependencies=[Depends(authorizer.require_operator)],
    )
    def rollback(workload: str):
        try:
            base_id = "qwen-base-triage" if workload == "change_triage" else "qwen-base"
            return database.activate_model(base_id, workload, action="rollback")
        except LookupError as exc:
            raise HTTPException(status_code=404, detail="base route not found") from exc

    @app.get("/v1/routes/{workload}", dependencies=[Depends(authorizer.require_viewer)])
    def route(workload: str):
        try:
            return database.active_model(workload)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get(
        "/v1/routes/{workload}/history",
        dependencies=[Depends(authorizer.require_viewer)],
    )
    def route_history(workload: str, limit: int = 50):
        return {"data": database.deployment_history(workload, max(1, min(limit, 200)))}

    @app.post("/v1/memory/import/git", dependencies=[Depends(authorizer.require_operator)])
    def import_git_memory(request: GitMemoryImportRequest):
        try:
            return memory.import_git(
                request.repository_path,
                commits=request.commits,
                max_commits=request.max_commits,
                include_diff_summary=request.include_diff_summary,
            )
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post(
        "/v1/memory/import/discussions",
        dependencies=[Depends(authorizer.require_operator)],
    )
    def import_discussion_memory(request: DiscussionMemoryImportRequest):
        try:
            return memory.import_discussions(request.file_path)
        except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/v1/memory/search", dependencies=[Depends(authorizer.require_operator)])
    def search_memory(q: str, limit: int = 5):
        if not q.strip():
            raise HTTPException(status_code=422, detail="q is required")
        return {"query": q, "data": memory.search(q, max(1, min(limit, 10)))}

    @app.post("/v1/memory/query", dependencies=[Depends(authorizer.require_operator)])
    def query_memory(request: MemoryQueryRequest):
        try:
            return memory.query(request.question, request.limit)
        except (FileNotFoundError, RuntimeError) as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get(
        "/v1/memory/sources/{source_id}",
        dependencies=[Depends(authorizer.require_operator)],
    )
    def memory_source(source_id: str):
        source = memory.source(source_id)
        if source is None:
            raise HTTPException(status_code=404, detail="memory source not found")
        return source

    @app.post(
        "/v1/hybrid/change-triage",
        dependencies=[Depends(authorizer.require_operator)],
    )
    def hybrid_change_triage(request: HybridTriageRequest):
        policy = deterministic_triage(request.content)
        if policy["resolved"]:
            return {**policy, "candidate": "triage-policy-v1", "route": "deterministic",
                    "adapter_used": False, "cloud_used": False}
        if not request.allow_cloud:
            return {**policy, "candidate": "triage-policy-v1", "route": "abstain",
                    "adapter_used": False, "cloud_used": False,
                    "next_action": "explicit cloud permission is required for fallback"}
        if not getattr(service.gemini, "configured", False):
            return {**policy, "candidate": "triage-policy-v1", "route": "abstain",
                    "adapter_used": False, "cloud_used": False,
                    "next_action": "Gemini fallback is not configured"}
        try:
            generation = service.gemini.generate(
                [{"role": "system", "content": PRODUCTION_PROMPT},
                 {"role": "user", "content": request.content}], 60, 0.0
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return {**policy, "candidate": "triage-policy-v1", "route": "cloud",
                "adapter_used": False, "cloud_used": True, "result": generation.text,
                "model": generation.model, "prompt_tokens": generation.prompt_tokens,
                "completion_tokens": generation.completion_tokens}

    return app


app = create_app()
