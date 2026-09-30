import { NextResponse } from "next/server";
import { json } from "@/lib/http";
import { statusFor } from "@/lib/statuspage";

/** Ninety days of uptime per component and the last day's readings, for the status page. Same token as the rest. */
export async function GET(request: Request) {
  const history = await statusFor(request, "/internal/statuspage/history");
  if (history instanceof NextResponse) return history;
  return json(200, history);
}
