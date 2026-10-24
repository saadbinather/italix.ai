import "server-only";

import type { OperatorChatRequest } from "@/types/operator";
import type {
  LearningConfig,
  LearningJob,
  LearningJobMetrics,
  LearningModel,
  LearningQueue,
  LearningStudioData,
} from "@/types/learning";

const DEFAULT_API_URL = "http://127.0.0.1:8000";

export interface OperatorBackendResponse {
  status: number;
  body: unknown;
  traceId: string | null;
  latencyMs: number;
}

function backendUrl(): string {
  return (process.env.ITALIX_API_URL || DEFAULT_API_URL).replace(/\/$/, "");
}

function record(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function text(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function numeric(value: unknown, fallback = 0): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function nullableNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function nullableText(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.slice(0, 500) : null;
}

async function operatorGet(path: string): Promise<unknown> {
  const token = process.env.ITALIX_OPERATOR_TOKEN;
  if (!token) throw new Error("ITALIX operator credentials are not configured.");
  const response = await fetch(`${backendUrl()}${path}`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
    signal: AbortSignal.timeout(10_000),
  });
  if (!response.ok) throw new Error(`ITALIX backend returned HTTP ${response.status}.`);
  return response.json() as Promise<unknown>;
}

function sanitizeQueue(value: unknown, workload: string): LearningQueue {
  const queue = record(value);
  const rawCounts = record(queue.counts);
  const counts = Object.fromEntries(
    Object.entries(rawCounts)
      .filter((entry): entry is [string, number] => typeof entry[1] === "number" && Number.isFinite(entry[1]))
      .map(([key, count]) => [key.slice(0, 40), count]),
  );
  return {
    workload: text(queue.workload, workload),
    pending: numeric(queue.pending),
    minimum_examples: numeric(queue.minimum_examples, 10),
    enough_examples: queue.enough_examples === true,
    counts,
  };
}

function sanitizeConfig(value: unknown, workload: string): LearningConfig {
  const config = record(value);
  const resources = record(config.estimated_resources);
  return {
    workload: text(config.workload, workload),
    engine: text(config.engine, "Unknown"),
    base_model: text(config.base_model, "Unknown"),
    fine_tune_type: text(config.fine_tune_type, "Unknown"),
    rank: numeric(config.rank),
    trainable_layers: numeric(config.trainable_layers),
    optimizer_steps: numeric(config.optimizer_steps),
    learning_rate: numeric(config.learning_rate),
    batch_size: numeric(config.batch_size),
    max_sequence_length: numeric(config.max_sequence_length),
    cloud_required: config.cloud_required === true,
    estimated_resources: {
      duration_seconds: text(resources.duration_seconds, "Not available"),
      peak_mlx_memory_gb: numeric(resources.peak_mlx_memory_gb),
      trainable_parameters: numeric(resources.trainable_parameters),
    },
  };
}

function finalLoss(value: unknown): number | null {
  if (!Array.isArray(value) || value.length === 0) return null;
  const last = value[value.length - 1];
  if (typeof last === "number") return nullableNumber(last);
  return nullableNumber(record(last).loss);
}

function evaluationAggregate(metrics: Record<string, unknown>, candidateId: string | null) {
  const evaluation = record(metrics.evaluation);
  const directPassed = nullableNumber(evaluation.passed);
  const directTotal = nullableNumber(evaluation.total);
  if (directPassed !== null || directTotal !== null) return { passed: directPassed, total: directTotal };
  const candidates = Array.isArray(evaluation.candidates) ? evaluation.candidates : [];
  const normalized = candidateId?.replaceAll("-", "_");
  const selected = candidates.map(record).find((candidate) => candidate.name === normalized || candidate.name === candidateId);
  return { passed: nullableNumber(selected?.passed), total: nullableNumber(selected?.total) };
}

function sanitizeJob(value: unknown): LearningJob {
  const job = record(value);
  const metrics = record(job.metrics);
  const candidateId = nullableText(job.candidate_id);
  const aggregate = evaluationAggregate(metrics, candidateId);
  const safeMetrics: LearningJobMetrics = {
    duration_seconds: nullableNumber(metrics.duration_seconds),
    optimizer_steps: nullableNumber(metrics.optimizer_steps),
    train_examples: nullableNumber(metrics.train_examples),
    validation_examples: nullableNumber(metrics.validation_examples),
    peak_mlx_memory_gb: nullableNumber(metrics.peak_mlx_memory_gb),
    final_training_loss: finalLoss(metrics.training_losses),
    final_validation_loss: finalLoss(metrics.validation_losses),
    evaluation_passed: aggregate.passed,
    evaluation_total: aggregate.total,
    qualification_reason: nullableText(record(metrics.evaluation).qualification_reason),
  };
  return {
    id: numeric(job.id),
    workload: text(job.workload, "unknown"),
    example_count: numeric(job.example_count),
    status: text(job.status, "unknown"),
    candidate_id: candidateId,
    created_at: text(job.created_at),
    completed_at: nullableText(job.completed_at),
    metrics: safeMetrics,
  };
}

function modelAggregate(metrics: Record<string, unknown>, id: string) {
  const directPassed = nullableNumber(metrics.validation_passed ?? record(metrics.validation).passed ?? record(metrics.validation_evaluation).passed);
  const directTotal = nullableNumber(metrics.validation_total ?? record(metrics.validation).total ?? record(metrics.validation_evaluation).total);
  if (directPassed !== null || directTotal !== null) return { passed: directPassed, total: directTotal };
  const normalized = id.replaceAll("-", "_");
  const candidate = (Array.isArray(metrics.candidates) ? metrics.candidates : [])
    .map(record)
    .find((item) => item.name === id || item.name === normalized);
  return { passed: nullableNumber(candidate?.passed), total: nullableNumber(candidate?.total) };
}

function sanitizeModel(value: unknown): LearningModel | null {
  const model = record(value);
  const kind = model.kind;
  if (kind !== "base" && kind !== "adapter" && kind !== "system") return null;
  const id = text(model.id, "unknown");
  let metrics: Record<string, unknown> = {};
  if (typeof model.metrics_json === "string") {
    try { metrics = record(JSON.parse(model.metrics_json)); } catch {}
  }
  const aggregate = modelAggregate(metrics, id);
  return {
    id,
    workload: text(model.workload, "unknown"),
    kind,
    status: text(model.status, "unknown"),
    active: model.active === 1 || model.active === true,
    created_at: text(model.created_at),
    evaluation_passed: aggregate.passed,
    evaluation_total: aggregate.total,
    qualified: model.status === "qualified",
    qualification_reason: nullableText(metrics.qualification_reason ?? record(metrics.evaluation).qualification_reason),
  };
}

export async function getLearningStudioData(): Promise<LearningStudioData> {
  const workloads = ["pr_summary", "change_triage"] as const;
  const [queueValues, configValues, jobsValue, modelsValue] = await Promise.all([
    Promise.all(workloads.map((workload) => operatorGet(`/v1/training/queue?workload=${workload}`))),
    Promise.all(workloads.map((workload) => operatorGet(`/v1/training/config?workload=${workload}`))),
    operatorGet("/v1/training/jobs?limit=50"),
    operatorGet("/v1/models"),
  ]);
  const queues = queueValues.map((value, index) => sanitizeQueue(value, workloads[index]));
  const configurations = configValues.map((value, index) => sanitizeConfig(value, workloads[index]));
  const jobs = (Array.isArray(record(jobsValue).data) ? record(jobsValue).data as unknown[] : []).map(sanitizeJob);
  const models = (Array.isArray(record(modelsValue).data) ? record(modelsValue).data as unknown[] : [])
    .map(sanitizeModel)
    .filter((model): model is LearningModel => model !== null);
  const adapters = models.filter((model) => model.kind === "adapter");
  return {
    queues,
    configurations,
    jobs,
    models,
    summary: {
      pending_examples: queues.reduce((total, queue) => total + queue.pending, 0),
      ready_workloads: queues.filter((queue) => queue.enough_examples).length,
      completed_jobs: jobs.filter((job) => job.status === "completed").length,
      planned_jobs: jobs.filter((job) => job.status === "planned").length,
      failed_jobs: jobs.filter((job) => job.status === "failed").length,
      experimental_adapters: adapters.filter((model) => model.status.startsWith("experimental")).length,
      qualified_adapters: adapters.filter((model) => model.status === "qualified").length,
    },
  };
}

export async function createOperatorChatCompletion(
  request: OperatorChatRequest,
): Promise<OperatorBackendResponse> {
  const token = process.env.ITALIX_OPERATOR_TOKEN;
  if (!token) throw new Error("ITALIX operator credentials are not configured.");

  const started = performance.now();
  const response = await fetch(`${backendUrl()}/v1/chat/completions`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(request),
    cache: "no-store",
    signal: AbortSignal.timeout(120_000),
  });
  const contentType = response.headers.get("content-type") ?? "";
  const body: unknown = contentType.includes("application/json")
    ? await response.json()
    : { detail: "The ITALIX backend returned a non-JSON response." };
  return {
    status: response.status,
    body,
    traceId: response.headers.get("x-italix-trace-id"),
    latencyMs: performance.now() - started,
  };
}
