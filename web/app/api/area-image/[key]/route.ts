import { json } from "@/lib/http";
import { internal, passthrough, unavailable } from "@/lib/internal";

export const dynamic = "force-dynamic";

type Params = { params: Promise<{ key: string }> };

/** Area artwork the bot cached from maimai DX NET, by its key. */
export async function GET(_request: Request, { params }: Params) {
  const { key } = await params;
  if (!/^(banner_)?[0-9a-f]{6,40}$/.test(key)) return json(404, { ok: false, error: "not_found" });
  try {
    return passthrough(await internal(`/internal/area-image/${key}`));
  } catch {
    return unavailable();
  }
}
