import type {
  OperatorChatMessage,
  OperatorChatRequest,
  OperatorChatValidation,
} from "@/types/operator";

export const MAX_OPERATOR_BODY_BYTES = 64 * 1024;
export const MAX_MESSAGE_CONTENT_LENGTH = 20_000;
export const MAX_MESSAGES = 32;

const allowedKeys = new Set([
  "model",
  "messages",
  "max_tokens",
  "temperature",
  "stream",
  "workload",
  "capture",
  "allow_cloud",
]);
const roles = new Set(["system", "user", "assistant"]);
const workloads = new Set(["pr_summary", "change_triage"]);
const identifier = /^[a-zA-Z0-9][a-zA-Z0-9._/-]{0,127}$/;

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

export function isSameOrigin(request: Request): boolean {
  const origin = request.headers.get("origin");
  const host = request.headers.get("host");
  if (!origin || !host) return false;
  try {
    const supplied = new URL(origin);
    const requestProtocol = request.headers.get("x-forwarded-proto") ?? new URL(request.url).protocol.replace(":", "");
    return supplied.host === host && supplied.protocol === `${requestProtocol}:`;
  } catch {
    return false;
  }
}

export async function readJsonBody(
  request: Request,
  maximumBytes = MAX_OPERATOR_BODY_BYTES,
): Promise<{ ok: true; value: unknown } | { ok: false; status: number; message: string }> {
  if (!request.headers.get("content-type")?.toLowerCase().startsWith("application/json")) {
    return { ok: false, status: 415, message: "Content-Type must be application/json." };
  }

  const declaredLength = Number(request.headers.get("content-length"));
  if (Number.isFinite(declaredLength) && declaredLength > maximumBytes) {
    return { ok: false, status: 413, message: "Request body is too large." };
  }

  const text = await request.text();
  if (new TextEncoder().encode(text).byteLength > maximumBytes) {
    return { ok: false, status: 413, message: "Request body is too large." };
  }
  try {
    return { ok: true, value: JSON.parse(text) as unknown };
  } catch {
    return { ok: false, status: 400, message: "Request body must contain valid JSON." };
  }
}

export function validateOperatorChat(value: unknown): OperatorChatValidation {
  if (!isRecord(value)) return { ok: false, message: "Request body must be an object." };
  if (Object.keys(value).some((key) => !allowedKeys.has(key))) {
    return { ok: false, message: "Request contains unsupported parameters." };
  }
  if (!Array.isArray(value.messages) || value.messages.length < 1 || value.messages.length > MAX_MESSAGES) {
    return { ok: false, message: `messages must contain between 1 and ${MAX_MESSAGES} items.` };
  }

  const messages: OperatorChatMessage[] = [];
  for (const message of value.messages) {
    if (!isRecord(message) || Object.keys(message).some((key) => key !== "role" && key !== "content")) {
      return { ok: false, message: "Each message must contain only role and content." };
    }
    if (typeof message.role !== "string" || !roles.has(message.role)) {
      return { ok: false, message: "Message role must be system, user, or assistant." };
    }
    if (
      typeof message.content !== "string" ||
      message.content.trim().length === 0 ||
      message.content.length > MAX_MESSAGE_CONTENT_LENGTH
    ) {
      return { ok: false, message: `Message content must be 1-${MAX_MESSAGE_CONTENT_LENGTH} characters.` };
    }
    messages.push({ role: message.role as OperatorChatMessage["role"], content: message.content });
  }

  const model = value.model === undefined ? "italix-auto" : value.model;
  if (typeof model !== "string" || !identifier.test(model)) {
    return { ok: false, message: "model has an invalid format." };
  }
  const maxTokens = value.max_tokens === undefined ? 160 : value.max_tokens;
  if (!Number.isInteger(maxTokens) || (maxTokens as number) < 1 || (maxTokens as number) > 512) {
    return { ok: false, message: "max_tokens must be an integer between 1 and 512." };
  }
  const temperature = value.temperature === undefined ? 0 : value.temperature;
  if (typeof temperature !== "number" || !Number.isFinite(temperature) || temperature < 0 || temperature > 2) {
    return { ok: false, message: "temperature must be between 0 and 2." };
  }
  if (value.stream !== undefined && value.stream !== false) {
    return { ok: false, message: "Streaming is not supported." };
  }
  if (value.workload !== undefined && (typeof value.workload !== "string" || !workloads.has(value.workload))) {
    return { ok: false, message: "workload must be pr_summary or change_triage." };
  }
  if (value.capture !== undefined && typeof value.capture !== "boolean") {
    return { ok: false, message: "capture must be a boolean." };
  }
  if (value.allow_cloud !== undefined && typeof value.allow_cloud !== "boolean") {
    return { ok: false, message: "allow_cloud must be a boolean." };
  }

  const request: OperatorChatRequest = {
    model,
    messages,
    max_tokens: maxTokens as number,
    temperature,
    stream: false,
    capture: value.capture ?? false,
    allow_cloud: value.allow_cloud ?? false,
  };
  if (value.workload !== undefined) request.workload = value.workload as OperatorChatRequest["workload"];
  return { ok: true, value: request };
}
