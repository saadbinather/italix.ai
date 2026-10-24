import { NextRequest, NextResponse } from "next/server";

import { getLearningStudioData } from "@/lib/italix-operator";
import { OPERATOR_COOKIE, verifyOperatorSession } from "@/lib/operator-session";

export const runtime = "nodejs";

export async function GET(request: NextRequest) {
  try {
    if (!verifyOperatorSession(request.cookies.get(OPERATOR_COOKIE)?.value)) {
      return NextResponse.json(
        { detail: "Operator session required." },
        { status: 401, headers: { "Cache-Control": "no-store" } },
      );
    }
    const data = await getLearningStudioData();
    return NextResponse.json(data, { headers: { "Cache-Control": "no-store" } });
  } catch {
    return NextResponse.json(
      { detail: "Learning status is unavailable from the local ITALIX backend." },
      { status: 502, headers: { "Cache-Control": "no-store" } },
    );
  }
}
