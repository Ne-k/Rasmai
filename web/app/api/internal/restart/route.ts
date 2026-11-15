import { timingSafeEqual } from "node:crypto";
import { env } from "@/lib/env";
import { json } from "@/lib/http";

/** The bot asks the site to exit and Docker starts it again: how the developer panel restarts the site. Refused without the shared secret, so the public port cannot do it. */
export async function POST(request: Request) {
  const secret = Buffer.from(env.internalSecret());
  const given = Buffer.from(request.headers.get("x-rasmai-internal") ?? "");
  if (!secret.length || given.length !== secret.length || !timingSafeEqual(given, secret)) return json(404, { ok: false });
  setTimeout(() => process.exit(0), 300); // after the answer has gone out
  return json(200, { ok: true });
}
