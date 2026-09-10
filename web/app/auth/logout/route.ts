import { NextResponse } from "next/server";
import { json, sameOrigin } from "@/lib/http";
import { SESSION_COOKIE, cookieHeader } from "@/lib/session";

export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  if (!sameOrigin(request)) return json(403, { ok: false, error: "cross_origin" });
  return new NextResponse(null, { status: 204, headers: { "Set-Cookie": cookieHeader(SESSION_COOKIE, "", 0) } });
}
