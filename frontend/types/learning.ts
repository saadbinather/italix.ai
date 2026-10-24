export interface LearningQueue {
  workload: string;
  pending: number;
  minimum_examples: number;
  enough_examples: boolean;
  counts: Record<string, number>;
}

export interface LearningConfig {
  workload: string;
  engine: string;
  base_model: string;
  fine_tune_type: string;
  rank: number;
  trainable_layers: number;
  optimizer_steps: number;
  learning_rate: number;
  batch_size: number;
  max_sequence_length: number;
  cloud_required: boolean;
  estimated_resources: {
    duration_seconds: string;
    peak_mlx_memory_gb: number;
    trainable_parameters: number;
  };
}

export interface LearningJobMetrics {
  duration_seconds: number | null;
  optimizer_steps: number | null;
  train_examples: number | null;
  validation_examples: number | null;
  peak_mlx_memory_gb: number | null;
  final_training_loss: number | null;
  final_validation_loss: number | null;
  evaluation_passed: number | null;
  evaluation_total: number | null;
  qualification_reason: string | null;
}

export interface LearningJob {
  id: number;
  workload: string;
  example_count: number;
  status: string;
  candidate_id: string | null;
  created_at: string;
  completed_at: string | null;
  metrics: LearningJobMetrics;
}

export interface LearningModel {
  id: string;
  workload: string;
  kind: "base" | "adapter" | "system";
  status: string;
  active: boolean;
  created_at: string;
  evaluation_passed: number | null;
  evaluation_total: number | null;
  qualified: boolean;
  qualification_reason: string | null;
}

export interface LearningStudioData {
  queues: LearningQueue[];
  configurations: LearningConfig[];
  jobs: LearningJob[];
  models: LearningModel[];
  summary: {
    pending_examples: number;
    ready_workloads: number;
    completed_jobs: number;
    planned_jobs: number;
    failed_jobs: number;
    experimental_adapters: number;
    qualified_adapters: number;
  };
}
