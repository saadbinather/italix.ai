import { NextRequest, NextResponse } from "next/server";

import { createOperatorChatCompletion } from "@/lib/italix-operator";
import { isSameOrigin, readJsonBody, validateOperatorChat } from "@/lib/operator-request";
import { OPERATOR_COOKIE, verifyOperatorSession } from "@/lib/operator-session";

export const runtime = "nodejs";

function response(body: unknown, status: number) {
  return NextResponse.json(body, { status, headers: { "Cache-Control": "no-store" } });
}

export async function POST(request: NextRequest) {
  if (!isSameOrigin(request)) return response({ detail: "Same-origin request required." }, 403);
  try {
    if (!verifyOperatorSession(request.cookies.get(OPERATOR_COOKIE)?.value)) {
      return response({ detail: "Operator session required." }, 401);
    }
  } catch {
    return response({ detail: "Operator session is not configured." }, 503);
  }

  const parsed = await readJsonBody(request);
  if (!parsed.ok) return response({ detail: parsed.message }, parsed.status);
  const validated = validateOperatorChat(parsed.value);
  if (!validated.ok) return response({ detail: validated.message }, 400);

  try {
    const backend = await createOperatorChatCompletion(validated.value);
    const headers = new Headers({ "Cache-Control": "no-store" });
    if (backend.traceId) headers.set("x-italix-trace-id", backend.traceId);
    headers.set("x-italix-latency-ms", backend.latencyMs.toFixed(1));
    return NextResponse.json(backend.body, { status: backend.status, headers });
  } catch {
    return response({ detail: "The local ITALIX backend is unavailable." }, 502);
  }
}
