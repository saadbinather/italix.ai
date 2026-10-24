"""Transparent workload detection and model-route decisions."""

from __future__ import annotations

from dataclasses import dataclass

from italix.database import Database


@dataclass(frozen=True)
class RouteDecision:
    route: str
    model_id: str
    reason: str


def identify_workload(messages: list[dict], explicit: str | None) -> str:
    if explicit:
        return explicit
    text = "\n".join(message["content"] for message in messages)
    if "diff --git" in text or "pull-request summary" in text.lower() or "pr summary" in text.lower():
        return "pr_summary"
    return "general"


class Router:
    def __init__(self, database: Database):
        self.database = database

    def decide(self, workload: str, requested_model: str, allow_cloud: bool) -> RouteDecision:
        requested = requested_model.lower()
        if requested in {"gemini", "gemini-2.5-flash"}:
            if not allow_cloud:
                raise PermissionError("cloud routing requires allow_cloud=true")
            return RouteDecision("cloud", "gemini", "explicit Gemini request with cloud opt-in")
        if requested in {"groq", "llama-3.1-8b-instant"}:
            if not allow_cloud:
                raise PermissionError("cloud routing requires allow_cloud=true")
            return RouteDecision("cloud", "groq", "explicit Groq request with cloud opt-in")
        if requested not in {"italix-auto", "auto"}:
            candidate = self.database.model(requested_model)
            if candidate is None:
                raise PermissionError(f"unknown local model: {requested_model}")
            if candidate["workload"] != workload:
                raise PermissionError("requested model does not support this workload")
            if candidate["kind"] == "system":
                if candidate["status"] != "validation_passed":
                    raise PermissionError("requested system candidate has not passed validation")
                return RouteDecision(
                    "deterministic",
                    candidate["id"],
                    f"explicit validated system candidate request: {candidate['id']}",
                )
            if not candidate["active"]:
                raise PermissionError("inactive adapters cannot be invoked directly")
            return RouteDecision(
                "local", candidate["id"], f"explicit active local model request: {candidate['id']}"
            )
        if workload not in {"pr_summary", "change_triage"}:
            return RouteDecision("local", "qwen-base", "general workload defaults to local base")
        active = self.database.active_model(workload)
        if active["kind"] == "system":
            if active["status"] != "validation_passed":
                raise PermissionError("active system route has not passed validation")
            return RouteDecision(
                "deterministic",
                active["id"],
                f"active validated system route for {workload} is {active['id']}",
            )
        return RouteDecision(
            "local",
            active["id"],
            f"active qualified route for {workload} is {active['id']}",
        )
