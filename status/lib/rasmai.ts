export type State = "operational" | "under_maintenance" | "degraded_performance" | "partial_outage" | "major_outage";

export type DayCounts = { up: number; degraded: number };
export type Day = { day: string; expected: number; samples: number; components: Record<string, DayCounts> };
export type Reading = { at: string; gatewayMs: number; waiting: number };

export type Snapshot =
  | { ok: false; at: number }
  | {
      ok: true;
      at: number;
      status: State;
      components: Record<string, State>;
      metrics: Record<string, number>;
      days: Day[];
      recent: Reading[];
    };

/** The public address of the main site, for the links back to it. */
export const siteUrl = () => (process.env.RASMAI_URL ?? "https://rasmai.lol").trim().replace(/\/+$/, "");

const TTL = 30_000;
let held: Snapshot | null = null;

async function get<T>(path: string): Promise<T> {
  const base = (process.env.RASMAI_URL ?? "").trim().replace(/\/+$/, "");
  const token = (process.env.RASMAI_STATUS_TOKEN ?? "").trim();
  if (!base || !token) throw new Error("RASMAI_URL and RASMAI_STATUS_TOKEN are not set");
  const response = await fetch(`${base}${path}`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: "no-store",
    signal: AbortSignal.timeout(8000),
  });
  if (!response.ok) throw new Error(`${path} answered ${response.status}`);
  return (await response.json()) as T;
}

/** What Rasmai says right now, read at most twice a minute per server instance.
 *
 * A failed read is kept for the same thirty seconds as a good one, and never replaced by an older good one:
 * a page that showed the last good answer through an outage would be hiding the outage. */
export async function snapshot(): Promise<Snapshot> {
  if (held && Date.now() - held.at < TTL) return held;
  let next: Snapshot;
  try {
    const [live, metrics, history] = await Promise.all([
      get<{ status: State; components: Record<string, State> }>("/api/statuspage"),
      get<{ metrics: Record<string, number> }>("/api/statuspage/metrics"),
      get<{ days: Day[]; recent: Reading[] }>("/api/statuspage/history"),
    ]);
    next = {
      ok: true,
      at: Date.now(),
      status: live.status,
      components: live.components,
      metrics: metrics.metrics ?? {},
      days: history.days ?? [],
      recent: history.recent ?? [],
    };
  } catch {
    next = { ok: false, at: Date.now() };
  }
  held = next;
  return next;
}
