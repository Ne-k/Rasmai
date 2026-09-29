import { json } from "@/lib/http";
import { internal, passthrough, unavailable } from "@/lib/internal";

type Params = { params: Promise<{ key: string }> };

/** A player's name plate the bot cached from maimai DX NET, by its key. */
export async function GET(_request: Request, { params }: Params) {
  const { key } = await params;
  if (!/^[0-9a-f]{40}$/.test(key)) return json(404, { ok: false, error: "not_found" });
  try {
    return passthrough(await internal(`/internal/nameplate/${key}`));
  } catch {
    return unavailable();
  }
}
