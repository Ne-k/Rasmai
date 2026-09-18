import { ImageResponse } from "next/og";
import { clientKey } from "@/lib/http";
import { internal } from "@/lib/internal";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const SLUG = /^[A-Za-z0-9_-]{10,64}$/;
const SIZE = { width: 1200, height: 630 };

// the plot, inside the card
const PLOT = { left: 92, top: 300, width: 1016, height: 218 };

// fewer points than this is not a line, it is a dot: those cards keep to the figures
const ENOUGH = 3;

type Point = { recordedAt?: string; rating?: number };
type Shared = {
  name?: string; rating?: number; region?: string; charts?: number; plays?: number;
  history?: Point[];
};

/** A date as the card says it: "Sep 3". */
function day(when: string): string {
  const at = new Date(when);
  return Number.isNaN(at.getTime())
    ? ""
    : at.toLocaleDateString("en", { month: "short", day: "numeric", timeZone: "UTC" });
}

/**
 * The picture of a shared profile: the rating over time, which is the one thing about a profile a
 * picture says better than a line of text.
 *
 * Discord shows this above the link, and the embed beside it already gives the name, the rating and
 * the chart count, so repeating those here would waste the only space that can hold a shape.
 *
 * Only what the page shows anyone holding the link. A profile that is switched off answers as if it
 * never existed, the same as the page does.
 */
export async function GET(request: Request, { params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  if (!SLUG.test(slug ?? "")) return new Response("not found", { status: 404 });
  let shared: Shared;
  try {
    const answer = await internal(`/internal/public/${slug}`, { client: clientKey(request) });
    if (!answer.ok) return new Response("not found", { status: 404 });
    shared = (await answer.json()) as Shared;
  } catch {
    return new Response("unavailable", { status: 503 });
  }
  const name = String(shared.name || "").trim();
  if (!name) return new Response("not found", { status: 404 });

  const region = String(shared.region || "intl").toUpperCase();
  const rating = Number(shared.rating || 0);
  const charts = Number(shared.charts || 0);
  const points = (shared.history ?? [])
    .map((row) => ({ at: String(row.recordedAt ?? ""), rating: Number(row.rating ?? 0) }))
    .filter((row) => row.rating > 0);

  // a run that never moves has no shape to draw, so the band is widened around it rather than
  // dividing by nothing
  const values = points.map((p) => p.rating);
  const low = Math.min(...values);
  const high = Math.max(...values);
  const span = high - low || Math.max(1, Math.round(high * 0.004));
  const at = (index: number, value: number) => [
    PLOT.left + (points.length > 1 ? (index / (points.length - 1)) * PLOT.width : PLOT.width / 2),
    PLOT.top + PLOT.height - ((value - low) / span) * PLOT.height,
  ];
  const line = points.map((p, i) => at(i, p.rating).join(",")).join(" ");
  const area = `${PLOT.left},${PLOT.top + PLOT.height} ${line} ${PLOT.left + PLOT.width},${PLOT.top + PLOT.height}`;
  const last = points[points.length - 1];
  const gain = points.length > 1 ? last.rating - points[0].rating : 0;
  const drawable = points.length >= ENOUGH;

  const figure = (label: string, value: string, tint = "#45d6f2") => (
    <div style={{ display: "flex", flexDirection: "column", marginRight: 70 }}>
      <div style={{ display: "flex", fontSize: 22, letterSpacing: 5, color: "#8d88a8", textTransform: "uppercase" }}>
        {label}
      </div>
      <div style={{ display: "flex", fontSize: 62, fontWeight: 800, color: tint, marginTop: 4 }}>{value}</div>
    </div>
  );

  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          position: "relative",
          background: "#14121c",
          color: "#f4f0e6",
          fontFamily: "sans-serif",
        }}
      >
        {/* the plot is drawn in the card's own coordinates, so it sits under the text rather than
            inside the padding that holds it */}
        {drawable ? (
          <svg
            width={SIZE.width}
            height={SIZE.height}
            viewBox={`0 0 ${SIZE.width} ${SIZE.height}`}
            style={{ position: "absolute", left: 0, top: 0, width: SIZE.width, height: SIZE.height }}
          >
            <polygon points={area} fill="#45d6f2" fillOpacity="0.14" />
            <polyline points={line} fill="none" stroke="#45d6f2" strokeWidth="5" strokeLinejoin="round" strokeLinecap="round" />
            {points.map((p, i) => {
              const [x, y] = at(i, p.rating);
              const last = i === points.length - 1;
              return (
                <circle key={i} cx={x} cy={y} r={last ? 10 : 5} fill={last ? "#ff5c9f" : "#14121c"}
                        stroke={last ? "#ff5c9f" : "#45d6f2"} strokeWidth="4" />
              );
            })}
          </svg>
        ) : null}

        {/* with no line to draw there is nothing holding the lower half, so the figures take the
            middle rather than sitting above an empty space */}
        <div style={{ display: "flex", flexDirection: "column", width: "100%",
                      padding: drawable ? "54px 92px 0" : "0 92px",
                      justifyContent: drawable ? "flex-start" : "center" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <div style={{ display: "flex", fontSize: 24, letterSpacing: 6, color: "#918ba6", textTransform: "uppercase" }}>
              {region} · {name}
            </div>
            <div style={{ display: "flex", fontSize: 36, fontWeight: 800 }}>
              Ras<span style={{ color: "#ff5c9f" }}>mai</span>
            </div>
          </div>

          <div style={{ display: "flex", marginTop: 26 }}>
            {figure("rating", rating.toLocaleString("en"))}
            {figure("charts", charts.toLocaleString("en"))}
            {drawable && gain !== 0
              ? figure(`since ${day(points[0].at)}`, `${gain > 0 ? "+" : ""}${gain}`, gain > 0 ? "#5ad18f" : "#ff5c9f")
              : null}
          </div>

          {drawable ? (
            <div style={{ display: "flex", justifyContent: "space-between", marginTop: PLOT.height + 78,
                          fontSize: 24, color: "#8d88a8" }}>
              <div style={{ display: "flex" }}>{day(points[0].at)}</div>
              <div style={{ display: "flex" }}>rating over time</div>
              <div style={{ display: "flex" }}>{day(last.at)}</div>
            </div>
          ) : (
            <div style={{ display: "flex", marginTop: 40, fontSize: 28, color: "#c6c0d4" }}>
              {Number(shared.plays || 0).toLocaleString("en")} plays
            </div>
          )}
        </div>
      </div>
    ),
    // a rating moves, and Discord re-reads a card when the page is posted again
    { ...SIZE, headers: { "Cache-Control": "public, max-age=300" } },
  );
}
