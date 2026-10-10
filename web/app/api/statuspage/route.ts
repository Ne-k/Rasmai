import { NextResponse } from "next/server";
import { json } from "@/lib/http";
import { statusFor } from "@/lib/statuspage";

// a part in any of these is still up: a slow one is still answering and maintenance is announced
const UP = new Set(["operational", "degraded_performance", "under_maintenance"]);

/** Component states in Statuspage's words, for the script that pushes them there. Needs `Authorization: Bearer $STATUSPAGE_TOKEN`.
 *
 * With `?component=bot` it answers for that one part through the status code, 200 while it is up and 503 while it is
 * not, for monitors that can only check the code, such as Instatus's. Its state is in the `X-Status` header too.
 * A part missing from the reading (the jobs while the bot is not running) counts as not up. */
export async function GET(request: Request) {
  const status = await statusFor(request);
  if (status instanceof NextResponse) return status;
  const part = new URL(request.url).searchParams.get("component");
  if (part !== null) {
    const state: string = (status.components ?? {})[part] ?? "unknown";
    const response = json(UP.has(state) ? 200 : 503, { ok: UP.has(state), component: part, state, time: new Date().toISOString() });
    response.headers.set("X-Status", state);
    return response;
  }
  return json(200, { ok: true, status: status.status, components: status.components, time: new Date().toISOString() });
}
