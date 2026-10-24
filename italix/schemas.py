"""HTTP request/response schemas for the Step 5 gateway."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1)


class ChatCompletionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str = "italix-auto"
    messages: list[ChatMessage] = Field(min_length=1)
    max_tokens: int = Field(default=160, ge=1, le=512)
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    stream: bool = False
    workload: str | None = None
    capture: bool = False
    allow_cloud: bool = False

    @model_validator(mode="after")
    def supported_mode(self):
        if self.stream:
            raise ValueError("streaming is not implemented in the hackathon MVP")
        return self


class FeedbackRequest(BaseModel):
    action: Literal["approve", "correct", "reject"]
    corrected_response: str | None = None

    @model_validator(mode="after")
    def correction_required(self):
        if self.action == "correct" and not (self.corrected_response or "").strip():
            raise ValueError("corrected_response is required for correct feedback")
        if self.action != "correct" and self.corrected_response is not None:
            raise ValueError("corrected_response is only valid with correct feedback")
        return self


class TrainingJobRequest(BaseModel):
    workload: str = "pr_summary"
    minimum_examples: int = Field(default=10, ge=1)
    candidate_id: str | None = Field(default=None, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    execute: bool = False


class ActivationRequest(BaseModel):
    workload: str = "pr_summary"


class ModelEvaluationRequest(BaseModel):
    workload: str = "pr_summary"
    split: Literal["valid"] = "valid"


class GitMemoryImportRequest(BaseModel):
    repository_path: str = Field(min_length=1)
    commits: list[str] | None = None
    max_commits: int = Field(default=50, ge=1, le=200)
    include_diff_summary: bool = False


class DiscussionMemoryImportRequest(BaseModel):
    file_path: str = Field(min_length=1)


class MemoryQueryRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    limit: int = Field(default=5, ge=1, le=10)


class HybridTriageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=20000)
    allow_cloud: bool = False


class OverviewActiveModel(BaseModel):
    id: str
    workload: str
    kind: Literal["base", "adapter", "system"]
    status: str


class OverviewObservedUsage(BaseModel):
    total_requests: int
    successful_requests: int
    failed_requests: int
    local_requests: int
    deterministic_requests: int
    model_inference_requests: int
    cloud_requests: int
    other_requests: int
    captured_interactions: int
    reviewed_interactions: int
    prompt_tokens: int
    completion_tokens: int


class OverviewLatencyMetrics(BaseModel):
    average_local_latency_ms: float | None
    average_deterministic_latency_ms: float | None
    average_model_inference_latency_ms: float | None
    average_cloud_latency_ms: float | None


class OverviewRegistryMetrics(BaseModel):
    deterministic_systems: int
    base_models: int
    experimental_lora_adapters: int
    qualified_lora_adapters: int
    active_deterministic_systems: int
    active_base_models: int
    active_lora_adapters: int


class OverviewCostMetrics(BaseModel):
    measured_cloud_cost_usd: float | None
    projected_cost_usd: float | None
    projection_configured: bool
    note: str


class OverviewLatestEvaluation(BaseModel):
    model_id: str
    status: str
    passed: int
    total: int
    qualified: bool


class OverviewLatestTrainingJob(BaseModel):
    id: int
    candidate_id: str | None
    status: str
    completed_at: str | None
    metrics: dict[str, Any]


class DashboardOverviewResponse(BaseModel):
    # Compatibility fields consumed by the existing Streamlit dashboard.
    total_requests: int
    successful_requests: int
    failed_requests: int
    local_requests: int
    deterministic_requests: int
    model_inference_requests: int
    cloud_requests: int
    other_requests: int
    captured_interactions: int
    reviewed_interactions: int
    prompt_tokens: int
    completion_tokens: int
    average_local_latency_ms: float | None
    average_deterministic_latency_ms: float | None
    average_model_inference_latency_ms: float | None
    average_cloud_latency_ms: float | None
    queue_pending: int
    queue_used: int
    queue_excluded: int
    training_jobs_completed: int
    active_models: list[OverviewActiveModel]
    latest_training_job: OverviewLatestTrainingJob | None
    latest_evaluation: OverviewLatestEvaluation | None
    measured_cloud_cost_usd: float | None
    cloud_cost_note: str

    # Structured contract for the Next.js migration.
    observed_usage: OverviewObservedUsage
    latency: OverviewLatencyMetrics
    registry: OverviewRegistryMetrics
    costs: OverviewCostMetrics
