import { json } from "@/lib/http";
import { internal, passthrough, unavailable } from "@/lib/internal";

export const dynamic = "force-dynamic";

type Params = { params: Promise<{ name: string }> };

/** Song jackets from the bot's chart-database cache. */
export async function GET(_request: Request, { params }: Params) {
  const { name } = await params;
  if (!/^[A-Za-z0-9_.-]{1,80}$/.test(name)) return json(404, { ok: false, error: "not_found" });
  try {
    return passthrough(await internal(`/internal/jacket/${encodeURIComponent(name)}`));
  } catch {
    return unavailable();
  }
}
