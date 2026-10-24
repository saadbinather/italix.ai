import "server-only";

import { createHmac, randomBytes, timingSafeEqual } from "node:crypto";

export const OPERATOR_COOKIE = "italix_operator_session";
export const OPERATOR_SESSION_SECONDS = 30 * 60;

function requiredSecret(name: "ITALIX_OPERATOR_UNLOCK_SECRET" | "ITALIX_SESSION_SECRET"): string {
  const secret = process.env[name] ?? "";
  if (secret.length < 32) throw new Error(`${name} must contain at least 32 characters.`);
  return secret;
}

function safelyEqual(left: string, right: string): boolean {
  const leftBytes = Buffer.from(left);
  const rightBytes = Buffer.from(right);
  if (leftBytes.length !== rightBytes.length) return false;
  return timingSafeEqual(leftBytes, rightBytes);
}

function signature(payload: string): string {
  return createHmac("sha256", requiredSecret("ITALIX_SESSION_SECRET"))
    .update(payload)
    .digest("base64url");
}

export function verifyUnlockSecret(candidate: unknown): boolean {
  if (typeof candidate !== "string") return false;
  return safelyEqual(candidate, requiredSecret("ITALIX_OPERATOR_UNLOCK_SECRET"));
}

export function createOperatorSession(now = Date.now()): string {
  const payload = Buffer.from(
    JSON.stringify({ version: 1, expires: now + OPERATOR_SESSION_SECONDS * 1000, nonce: randomBytes(16).toString("base64url") }),
  ).toString("base64url");
  return `${payload}.${signature(payload)}`;
}

export function verifyOperatorSession(value: string | undefined, now = Date.now()): boolean {
  if (!value) return false;
  const separator = value.lastIndexOf(".");
  if (separator < 1) return false;
  const payload = value.slice(0, separator);
  const suppliedSignature = value.slice(separator + 1);
  if (!safelyEqual(suppliedSignature, signature(payload))) return false;
  try {
    const parsed = JSON.parse(Buffer.from(payload, "base64url").toString("utf8")) as {
      version?: unknown;
      expires?: unknown;
    };
    return parsed.version === 1 && typeof parsed.expires === "number" && parsed.expires > now;
  } catch {
    return false;
  }
}
