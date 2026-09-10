import { json, redirect } from "@/lib/http";

export const dynamic = "force-dynamic";

type Params = { params: Promise<{ cover: string; type: string; difficulty: string }> };

const TIERS: Record<string, string> = { bas: "basic", adv: "advanced", exp: "expert", mas: "master", rem: "remaster", utg: "utage" };

/** The bot's short chart links: /c/<jacket id>/<std|dx>/<tier> opens the Look up tab on that chart. */
export async function GET(_request: Request, { params }: Params) {
  const { cover, type, difficulty } = await params;
  if (!/^[A-Za-z0-9_-]{1,80}$/.test(cover)) return json(404, { ok: false, error: "not_found" });
  const kind = type === "dx" ? "dx" : "std";
  const tier = TIERS[difficulty] ?? (Object.values(TIERS).includes(difficulty) ? difficulty : "master");
  return redirect(`/me/?cover=${encodeURIComponent(cover)}&type=${kind}&difficulty=${tier}#chart`);
}
