export type ActiveModelKind = "base" | "adapter" | "system";

export interface ActiveModel {
  id: string;
  workload: string;
  kind: ActiveModelKind;
  status: string;
}

export interface ObservedUsage {
  total_requests: number;
  successful_requests: number;
  failed_requests: number;
  local_requests: number;
  deterministic_requests: number;
  model_inference_requests: number;
  cloud_requests: number;
  other_requests: number;
  captured_interactions: number;
  reviewed_interactions: number;
  prompt_tokens: number;
  completion_tokens: number;
}

export interface LatencyMetrics {
  average_local_latency_ms: number | null;
  average_deterministic_latency_ms: number | null;
  average_model_inference_latency_ms: number | null;
  average_cloud_latency_ms: number | null;
}

export interface RegistryMetrics {
  deterministic_systems: number;
  base_models: number;
  experimental_lora_adapters: number;
  qualified_lora_adapters: number;
  active_deterministic_systems: number;
  active_base_models: number;
  active_lora_adapters: number;
}

export interface CostMetrics {
  measured_cloud_cost_usd: number | null;
  projected_cost_usd: number | null;
  projection_configured: boolean;
  note: string;
}

export interface LatestTrainingJob {
  id: number;
  candidate_id: string | null;
  status: string;
  completed_at: string | null;
  metrics: Record<string, unknown>;
}

export interface LatestEvaluation {
  model_id: string;
  status: string;
  passed: number;
  total: number;
  qualified: boolean;
}

export interface DashboardOverview {
  total_requests: number;
  successful_requests: number;
  failed_requests: number;
  local_requests: number;
  deterministic_requests: number;
  model_inference_requests: number;
  cloud_requests: number;
  other_requests: number;
  captured_interactions: number;
  reviewed_interactions: number;
  prompt_tokens: number;
  completion_tokens: number;
  average_local_latency_ms: number | null;
  average_deterministic_latency_ms: number | null;
  average_model_inference_latency_ms: number | null;
  average_cloud_latency_ms: number | null;
  queue_pending: number;
  queue_used: number;
  queue_excluded: number;
  training_jobs_completed: number;
  active_models: ActiveModel[];
  latest_training_job: LatestTrainingJob | null;
  latest_evaluation: LatestEvaluation | null;
  measured_cloud_cost_usd: number | null;
  cloud_cost_note: string;
  observed_usage: ObservedUsage;
  latency: LatencyMetrics;
  registry: RegistryMetrics;
  costs: CostMetrics;
}

export type OverviewResult =
  | { ok: true; overview: DashboardOverview }
  | {
      ok: false;
      kind: "configuration" | "authentication" | "backend" | "response";
      message: string;
    };
