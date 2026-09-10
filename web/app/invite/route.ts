import { env } from "@/lib/env";
import { json, redirect } from "@/lib/http";

export const dynamic = "force-dynamic";

export async function GET() {
  const invite = env.botInvite();
  if (!invite) return json(404, { ok: false, error: "no_invite_configured" });
  return redirect(invite);
}
