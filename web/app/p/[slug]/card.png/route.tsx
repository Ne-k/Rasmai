import { ImageResponse } from "next/og";
import { internal } from "@/lib/internal";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const SLUG = /^[A-Za-z0-9_-]{16,64}$/;
const SIZE = { width: 1200, height: 630 };

type Shared = { name?: string; rating?: number; region?: string; charts?: number; plays?: number; dan?: string };

/**
 * The picture of a shared profile: what Discord shows above the link, and the page's own card.
 *
 * Only the header the page shows anyone holding the link. A profile that is switched off answers as
 * if it never existed, the same as the page does.
 */
export async function GET(_request: Request, { params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  if (!SLUG.test(slug ?? "")) return new Response("not found", { status: 404 });
  let shared: Shared;
  try {
    const answer = await internal(`/internal/public/${slug}`);
    if (!answer.ok) return new Response("not found", { status: 404 });
    shared = (await answer.json()) as Shared;
  } catch {
    return new Response("unavailable", { status: 503 });
  }
  const name = String(shared.name || "").trim();
  if (!name) return new Response("not found", { status: 404 });

  const rating = Number(shared.rating || 0).toLocaleString("en");
  const charts = Number(shared.charts || 0).toLocaleString("en");
  const plays = Number(shared.plays || 0);
  const region = String(shared.region || "intl").toUpperCase();
  // a long name has to fit the width rather than run off it
  const nameSize = name.length > 18 ? 66 : name.length > 12 ? 84 : 104;

  const figure = (label: string, value: string) => (
    <div style={{ display: "flex", flexDirection: "column", marginRight: 74 }}>
      <div style={{ display: "flex", fontSize: 24, letterSpacing: 5, color: "#8d88a8", textTransform: "uppercase" }}>
        {label}
      </div>
      <div style={{ display: "flex", fontSize: 76, fontWeight: 800, color: "#45d6f2", marginTop: 6 }}>{value}</div>
    </div>
  );

  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          padding: "0 92px",
          background: "#14121c",
          color: "#f4f0e6",
          fontFamily: "sans-serif",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div style={{ display: "flex", fontSize: 26, letterSpacing: 6, color: "#918ba6", textTransform: "uppercase" }}>
            {region} · shared profile
          </div>
          <div style={{ display: "flex", fontSize: 40, fontWeight: 800 }}>
            Ras<span style={{ color: "#ff5c9f" }}>mai</span>
          </div>
        </div>
        <div style={{ display: "flex", fontSize: nameSize, fontWeight: 800, lineHeight: 1.1, marginTop: 14 }}>{name}</div>
        {plays > 0 ? (
          <div style={{ display: "flex", fontSize: 28, color: "#c6c0d4", marginTop: 8 }}>
            {plays.toLocaleString("en")} plays
          </div>
        ) : null}
        <div style={{ display: "flex", marginTop: 46 }}>
          {figure("rating", rating)}
          {figure("charts", charts)}
        </div>
        <div style={{ display: "flex", marginTop: 44, fontSize: 26, color: "#8d88a8", letterSpacing: 2 }}>rasmai.lol</div>
      </div>
    ),
    // Discord re-reads a card when the page is posted again, and a rating moves
    { ...SIZE, headers: { "Cache-Control": "public, max-age=300" } },
  );
}
