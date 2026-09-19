import { ImageResponse } from "next/og";
import { clientKey } from "@/lib/http";
import { internal } from "@/lib/internal";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const SLUG = /^[A-Za-z0-9_-]{10,64}$/;

// shorter than the 1200x630 a link preview usually is. Discord gives a picture the full width of
// the card whatever shape it is, so a tall one pushes the text and the buttons down the screen.
const SIZE = { width: 1100, height: 420 };

// the plot, inside the card
const PLOT = { left: 64, top: 226, width: 972, height: 118 };

// fewer points than this is not a line, it is a dot: those cards keep to the figures
const ENOUGH = 3;

type Point = { recordedAt?: string; rating?: number };
type Chart = { rating?: number };
type Family = { label?: string; offset?: number };
type Card = { on?: boolean; chart?: boolean; gain?: boolean; charts?: boolean; plays?: boolean };
type Shared = {
  name?: string; rating?: number; region?: string; charts?: number; plays?: number;
  history?: Point[]; card?: Card; colour?: string; visual?: string;
  best50?: { new?: Chart[]; old?: Chart[] };
  traitFamilies?: Family[];
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
 * What goes on it is the owner's choice, made in the Account tab. The name and the rating are the
 * card, so they are always here; everything beside them can be switched off, and so can the curve.
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

  const wants: Card = { on: true, chart: true, gain: true, charts: true, plays: false, ...(shared.card ?? {}) };
  // the owner's colour, or the brand's when there is not one. Checked again here because this is
  // drawn straight into the markup and a colour is the one field that is not a yes or a no.
  const tint = /^#[0-9a-f]{6}$/i.test(String(shared.colour ?? "")) ? String(shared.colour) : "#ff3d8f";
  const region = String(shared.region || "intl").toUpperCase();
  const rating = Number(shared.rating || 0);
  const charts = Number(shared.charts || 0);
  const plays = Number(shared.plays || 0);
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

  // the fifty charts the rating is made of, tallest first: a skyline of where the rating comes from
  const best = [...(shared.best50?.new ?? []), ...(shared.best50?.old ?? [])]
    .map((row) => Number(row.rating ?? 0))
    .filter((value) => value > 0)
    .sort((a, b) => b - a);
  const skyline = () => {
    const top = Math.max(...best);
    const foot = Math.min(...best);
    const reach = top - foot || 1;
    const step = PLOT.width / best.length;
    return best.map((value, i) => {
      // a bar is never nothing, so the shortest still reads as a bar rather than a gap
      const tall = 16 + ((value - foot) / reach) * (PLOT.height - 16);
      return (
        <rect key={i} x={PLOT.left + i * step} y={PLOT.top + PLOT.height - tall}
              width={Math.max(2, step - 3)} height={tall} fill={tint}
              fillOpacity={i < 15 ? 0.95 : 0.55} />
      );
    });
  };

  // the five or six groups the traits roll up into, as a wheel. The middle ring is their own
  // average, so a point outside it is a group they beat themselves on.
  const families = (shared.traitFamilies ?? [])
    .map((row) => ({ label: String(row.label ?? ""), offset: Number(row.offset ?? 0) }))
    .filter((row) => row.label)
    .slice(0, 8);
  // left of centre and a little smaller, so the longest group name still has room to sit beside it
  const wheel = { x: 818, y: 226, r: 94 };
  const corner = (i: number, scale: number) => {
    const turn = (i / families.length) * Math.PI * 2 - Math.PI / 2;
    return [wheel.x + Math.cos(turn) * wheel.r * scale, wheel.y + Math.sin(turn) * wheel.r * scale];
  };
  // the widest gap sets the edge, so a wheel is never all rim or all centre
  const widest = Math.max(0.35, ...families.map((row) => Math.abs(row.offset)));
  const ring = (scale: number) => families.map((_, i) => corner(i, scale).join(",")).join(" ");
  const shape = families.map((row, i) => corner(i, 0.45 + (row.offset / widest) * 0.45).join(",")).join(" ");

  // the owner's pick, unless the thing it draws is not there, in which case the figures stand alone
  const asked = String(shared.visual ?? "curve");
  const visual = asked === "curve" && points.length < ENOUGH ? "figures"
    : asked === "best50" && best.length < 5 ? "figures"
    : asked === "traits" && families.length < 3 ? "figures"
    : asked;
  const drawable = wants.chart !== false && visual !== "figures";

  // every picture is a flat list of marks rather than a fragment: Satori draws an array inside an
  // svg and chokes on a fragment there, which is a blank card and no error anybody would see
  const marks = (): React.ReactNode[] => {
    if (visual === "curve") {
      return [
        <polygon key="fill" points={area} fill={tint} fillOpacity="0.14" />,
        <polyline key="line" points={line} fill="none" stroke={tint} strokeWidth="4"
                  strokeLinejoin="round" strokeLinecap="round" />,
        ...points.map((p, i) => {
          const [x, y] = at(i, p.rating);
          const tip = i === points.length - 1;
          return (
            <circle key={`p${i}`} cx={x} cy={y} r={tip ? 8 : 4} fill={tip ? "#f4f0e6" : "#14121c"}
                    stroke={tip ? "#f4f0e6" : tint} strokeWidth="3" />
          );
        }),
      ];
    }
    if (visual === "best50") return skyline();
    if (visual === "traits") {
      return [
        ...[1, 0.66, 0.33].map((scale) => (
          <polygon key={`r${scale}`} points={ring(scale)} fill="none" stroke="#2b2742" strokeWidth="1.5" />
        )),
        <polygon key="mid" points={ring(0.45)} fill="none" stroke="#3d3857" strokeWidth="2" strokeDasharray="4 4" />,
        <polygon key="them" points={shape} fill={tint} fillOpacity="0.2" stroke={tint} strokeWidth="3"
                 strokeLinejoin="round" />,
      ];
    }
    return [];
  };

  const figure = (label: string, value: string, ink = tint) => (
    <div style={{ display: "flex", flexDirection: "column", marginRight: 54 }}>
      <div style={{ display: "flex", fontSize: 18, letterSpacing: 4, color: "#8d88a8", textTransform: "uppercase" }}>
        {label}
      </div>
      <div style={{ display: "flex", fontSize: 50, fontWeight: 800, color: ink, marginTop: 2 }}>{value}</div>
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
            {marks()}
          </svg>
        ) : null}

        {/* Satori draws no text inside an svg, so the wheel's labels sit over it as their own layer */}
        {visual === "traits"
          ? families.map((row, i) => {
              const [x, y] = corner(i, 1.26);
              const right = x > wheel.x + 6;
              const middle = Math.abs(x - wheel.x) <= 6;
              return (
                <div
                  key={row.label}
                  style={{
                    display: "flex", position: "absolute", top: y - 10, fontSize: 15, color: "#8d88a8",
                    ...(middle
                      ? { left: x - 80, width: 160, justifyContent: "center" }
                      : right
                        ? { left: x }
                        : { right: SIZE.width - x }),
                  }}
                >
                  {row.label}
                </div>
              );
            })
          : null}

        {/* with no line to draw there is nothing holding the lower half, so the figures take the
            middle rather than sitting above an empty space */}
        <div style={{ display: "flex", flexDirection: "column", width: "100%",
                      padding: drawable ? "36px 64px 0" : "0 64px",
                      justifyContent: drawable ? "flex-start" : "center" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <div style={{ display: "flex", fontSize: 20, letterSpacing: 5, color: "#918ba6", textTransform: "uppercase" }}>
              {region} · {name}
            </div>
            <div style={{ display: "flex", fontSize: 30, fontWeight: 800 }}>
              Ras<span style={{ color: tint }}>mai</span>
            </div>
          </div>

          <div style={{ display: "flex", marginTop: 20 }}>
            {figure("rating", rating.toLocaleString("en"))}
            {wants.charts !== false ? figure("charts", charts.toLocaleString("en")) : null}
            {wants.plays ? figure("plays", plays.toLocaleString("en")) : null}
            {wants.gain !== false && drawable && gain !== 0
              ? figure(`since ${day(points[0].at)}`, `${gain > 0 ? "+" : ""}${gain}`, gain > 0 ? "#5ad18f" : "#ff5c9f")
              : null}
          </div>

          {drawable ? (
            <div style={{ display: "flex", justifyContent: "space-between", marginTop: PLOT.height + 56,
                          fontSize: 19, color: "#8d88a8" }}>
              <div style={{ display: "flex" }}>{visual === "curve" ? day(points[0].at) : ""}</div>
              <div style={{ display: "flex" }}>
                {visual === "curve" ? "rating over time"
                  : visual === "best50" ? `the ${best.length} charts your rating is made of`
                  : "what each part of your play asks"}
              </div>
              <div style={{ display: "flex" }}>{visual === "curve" ? day(last.at) : ""}</div>
            </div>
          ) : null}
        </div>
      </div>
    ),
    // a rating moves, and Discord re-reads a card when the page is posted again
    { ...SIZE, headers: { "Cache-Control": "public, max-age=300" } },
  );
}
