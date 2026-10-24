export type OperatorMessageRole = "system" | "user" | "assistant";

export interface OperatorChatMessage {
  role: OperatorMessageRole;
  content: string;
}

export interface OperatorChatRequest {
  model: string;
  messages: OperatorChatMessage[];
  max_tokens: number;
  temperature: number;
  stream: false;
  workload?: "pr_summary" | "change_triage";
  capture: boolean;
  allow_cloud: boolean;
}

export type OperatorChatValidation =
  | { ok: true; value: OperatorChatRequest }
  | { ok: false; message: string };
