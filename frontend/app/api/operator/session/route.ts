import { NextResponse } from "next/server";
import { cookies } from "next/headers";

import { isSameOrigin, readJsonBody } from "@/lib/operator-request";
import {
  createOperatorSession,
  OPERATOR_COOKIE,
  OPERATOR_SESSION_SECONDS,
  verifyUnlockSecret,
  verifyOperatorSession,
} from "@/lib/operator-session";

export const runtime = "nodejs";

function response(message: string, status: number) {
  return NextResponse.json({ detail: message }, { status, headers: { "Cache-Control": "no-store" } });
}

export async function GET() {
  try {
    const cookieStore = await cookies();
    const authenticated = verifyOperatorSession(cookieStore.get(OPERATOR_COOKIE)?.value);
    return NextResponse.json({ authenticated }, { headers: { "Cache-Control": "no-store" } });
  } catch {
    return NextResponse.json(
      { authenticated: false, configured: false },
      { status: 503, headers: { "Cache-Control": "no-store" } },
    );
  }
}

export async function POST(request: Request) {
  if (!isSameOrigin(request)) return response("Same-origin request required.", 403);
  const parsed = await readJsonBody(request, 4 * 1024);
  if (!parsed.ok) return response(parsed.message, parsed.status);
  const value = parsed.value;
  const secret = value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>).secret
    : undefined;
  try {
    if (!verifyUnlockSecret(secret)) return response("Invalid operator unlock credentials.", 401);
    const nextResponse = response("Operator session unlocked.", 200);
    nextResponse.cookies.set(OPERATOR_COOKIE, createOperatorSession(), {
      httpOnly: true,
      secure: true,
      sameSite: "strict",
      path: "/api/operator",
      maxAge: OPERATOR_SESSION_SECONDS,
    });
    return nextResponse;
  } catch {
    return response("Operator session is not configured.", 503);
  }
}

export async function DELETE(request: Request) {
  if (!isSameOrigin(request)) return response("Same-origin request required.", 403);
  const nextResponse = response("Operator session locked.", 200);
  nextResponse.cookies.set(OPERATOR_COOKIE, "", {
    httpOnly: true,
    secure: true,
    sameSite: "strict",
    path: "/api/operator",
    maxAge: 0,
  });
  return nextResponse;
}
