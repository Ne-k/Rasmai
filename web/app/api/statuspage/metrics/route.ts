import { NextResponse } from "next/server";
import { json } from "@/lib/http";
import { statusFor } from "@/lib/statuspage";

/** Numbers for Statuspage's metric graphs: gateway latency, people waiting on a build, reads in flight. Same token as the components. */
export async function GET(request: Request) {
  const status = await statusFor(request);
  if (status instanceof NextResponse) return status;
  return json(200, { ok: true, metrics: status.metrics, time: new Date().toISOString() });
}
