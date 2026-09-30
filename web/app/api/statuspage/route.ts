import { NextResponse } from "next/server";
import { json } from "@/lib/http";
import { statusFor } from "@/lib/statuspage";

/** Component states in Statuspage's words, for the script that pushes them there. Needs `Authorization: Bearer $STATUSPAGE_TOKEN`. */
export async function GET(request: Request) {
  const status = await statusFor(request);
  if (status instanceof NextResponse) return status;
  return json(200, { ok: true, status: status.status, components: status.components, time: new Date().toISOString() });
}
