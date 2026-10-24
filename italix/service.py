"""Observe → route → infer → persist orchestration."""

from __future__ import annotations

import json
import time
import uuid

from italix.database import Database, utc_now
from italix.change_triage import validate_triage_output
from italix.engines import Engine, Generation, prepare_messages
from italix.routing import Router, identify_workload
from italix.schemas import ChatCompletionRequest


class GatewayService:
    def __init__(
        self,
        database: Database,
        local: Engine,
        gemini: Engine,
        groq: Engine,
        deterministic_pr: Engine,
    ):
        self.database = database
        self.local = local
        self.gemini = gemini
        self.groq = groq
        self.deterministic_pr = deterministic_pr
        self.router = Router(database)

    def complete(self, request: ChatCompletionRequest) -> tuple[dict, str]:
        original_messages = [message.model_dump() for message in request.messages]
        workload = identify_workload(original_messages, request.workload)
        decision = self.router.decide(workload, request.model, request.allow_cloud)
        selected_route = decision.route
        selected_model = decision.model_id
        routing_reason = decision.reason
        messages = prepare_messages(workload, original_messages)
        trace_id = f"trace_{uuid.uuid4().hex}"
        started = time.perf_counter()
        error = None
        try:
            if selected_route == "deterministic":
                generation = self.deterministic_pr.generate(
                    original_messages, request.max_tokens, request.temperature
                )
            elif selected_route == "local":
                try:
                    adapter_path = None
                    if selected_model != "qwen-base":
                        adapter_path = self.database.active_model(workload)["path"]
                    generation = self.local.generate(
                        messages, request.max_tokens, request.temperature, adapter_path=adapter_path
                    )
                except Exception:
                    if not request.allow_cloud or not getattr(self.gemini, "configured", False):
                        raise
                    generation = self.gemini.generate(messages, request.max_tokens, request.temperature)
                    selected_route = "cloud"
                    selected_model = "gemini"
                    routing_reason = "local inference failed; Gemini fallback explicitly allowed"
            elif selected_model == "gemini":
                generation = self.gemini.generate(messages, request.max_tokens, request.temperature)
            else:
                generation = self.groq.generate(messages, request.max_tokens, request.temperature)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            latency_ms = (time.perf_counter() - started) * 1000
            if error:
                self.database.insert_trace(
                    {
                        "id": trace_id,
                        "created_at": utc_now(),
                        "workload": workload,
                        "requested_model": request.model,
                        "selected_model": selected_model,
                        "route": selected_route,
                        "routing_reason": routing_reason,
                        "capture_enabled": int(request.capture),
                        "prompt_json": json.dumps(original_messages) if request.capture else None,
                        "response_text": None,
                        "prompt_tokens": None,
                        "completion_tokens": None,
                        "latency_ms": latency_ms,
                        "validation_json": json.dumps({"inference_succeeded": False}),
                        "error": error,
                    }
                )
        latency_ms = (time.perf_counter() - started) * 1000
        validation = {
            "inference_succeeded": True,
            "adapter_qualified": selected_model in {"qwen-base", "qwen-base-triage"},
        }
        if selected_route == "deterministic":
            validation["deterministic_pr_summary"] = (generation.metadata or {}).get("validation")
            validation["abstained"] = bool((generation.metadata or {}).get("abstained"))
            validation["abstention_reasons"] = (generation.metadata or {}).get(
                "abstention_reasons", []
            )
        if workload == "change_triage":
            validation["change_triage"] = validate_triage_output(
                generation.text, "\n".join(message["content"] for message in original_messages)
            )
        self.database.insert_trace(
            {
                "id": trace_id,
                "created_at": utc_now(),
                "workload": workload,
                "requested_model": request.model,
                "selected_model": selected_model,
                "route": selected_route,
                "routing_reason": routing_reason,
                "capture_enabled": int(request.capture),
                "prompt_json": json.dumps(original_messages) if request.capture else None,
                "response_text": generation.text if request.capture else None,
                "prompt_tokens": generation.prompt_tokens,
                "completion_tokens": generation.completion_tokens,
                "latency_ms": latency_ms,
                "validation_json": json.dumps(validation),
                "error": None,
            }
        )
        created = int(time.time())
        body = {
            "id": f"chatcmpl-{uuid.uuid4().hex}",
            "object": "chat.completion",
            "created": created,
            "model": generation.model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": generation.text},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": generation.prompt_tokens,
                "completion_tokens": generation.completion_tokens,
                "total_tokens": (
                    generation.prompt_tokens + generation.completion_tokens
                    if generation.prompt_tokens is not None and generation.completion_tokens is not None
                    else None
                ),
            },
            "italix": {
                "trace_id": trace_id,
                "workload": workload,
                "route": selected_route,
                "registry_model": selected_model,
                "routing_reason": routing_reason,
                "capture_enabled": request.capture,
                "validation": validation.get("change_triage"),
                "deterministic_validation": validation.get("deterministic_pr_summary"),
                "abstained": validation.get("abstained", False),
                "abstention_reasons": validation.get("abstention_reasons", []),
                "adapter_used": bool((generation.metadata or {}).get("adapter_used", False)),
            },
        }
        return body, trace_id
