import { env } from "@/lib/env";
import { redirect } from "@/lib/http";

export async function GET() {
  return redirect(env.supportInvite());
}
