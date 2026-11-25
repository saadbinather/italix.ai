import { NextRequest, NextResponse } from "next/server";

import { createOperatorHybridTriage } from "@/lib/italix-operator";
import { isSameOrigin, readJsonBody } from "@/lib/operator-request";
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
  const body = parsed.value;
  if (!body || typeof body !== "object" || Array.isArray(body)) {
    return response({ detail: "A patch and explanation option are required." }, 400);
  }
  const { content, explain } = body as Record<string, unknown>;
  if (Object.keys(body).length !== 2 || typeof content !== "string"
      || !content.trim() || content.length > 20_000 || typeof explain !== "boolean") {
    return response({ detail: "Provide a nonempty patch of up to 20,000 characters and an explanation option." }, 400);
  }

  try {
    const backend = await createOperatorHybridTriage({ content, explain });
    return response(backend.body, backend.status);
  } catch {
    return response({ detail: "The local ITALIX backend is unavailable." }, 502);
  }
}
