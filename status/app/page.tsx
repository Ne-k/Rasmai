import { Ring } from "@/components/Ring";
import { ThemeToggle } from "@/components/Theme";
import { siteUrl, snapshot, type Day, type Reading, type Snapshot, type State } from "@/lib/rasmai";

export const dynamic = "force-dynamic";

const NAMES: Record<string, string> = {
  bot: "Discord bot",
  maimai: "maimai DX NET",
  analysis: "Dashboard analysis",
  database: "Database",
};
const ORDER = Object.keys(NAMES);
const DAYS = 90;

type Word = State | "unreachable";

const WORDS: Record<Word, { label: string; tone: string }> = {
  operational: { label: "operational", tone: "ok" },
  under_maintenance: { label: "maintenance", tone: "maintenance" },
  degraded_performance: { label: "degraded", tone: "warn" },
  partial_outage: { label: "partial outage", tone: "down" },
  major_outage: { label: "outage", tone: "down" },
  unreachable: { label: "unknown", tone: "none" },
};

const HEADLINE: Record<Word, { before: string; em: string; after: string; lede: string }> = {
  operational: { before: "Everything is ", em: "up", after: ".", lede: "The bot, the dashboard and maimai DX NET are all answering." },
  under_maintenance: { before: "Down for ", em: "maintenance", after: ".", lede: "maimai DX NET is in its scheduled maintenance window. Your saved scores still work." },
  degraded_performance: { before: "Running a little ", em: "slow", after: ".", lede: "Everything is answering, but something is slower than usual." },
  partial_outage: { before: "Part of Rasmai is ", em: "down", after: ".", lede: "Some things will not work until it is back." },
  major_outage: { before: "Rasmai is ", em: "down", after: ".", lede: "The bot is not answering. It is usually back within a few minutes." },
  unreachable: { before: "Can't ", em: "reach", after: " Rasmai.", lede: "This page could not get an answer from the bot or its website, so it can't say more." },
};

const isoDay = (offset: number) => new Date(Date.now() - offset * 86_400_000).toISOString().slice(0, 10);

/** One cell per day for the last ninety, oldest first; a day with no record is left empty rather than guessed. */
function cells(days: Day[], name: string) {
  const byDay = new Map(days.map((d) => [d.day, d]));
  let up = 0;
  let expected = 0;
  const out = Array.from({ length: DAYS }, (_, i) => {
    const day = isoDay(DAYS - 1 - i);
    const held = byDay.get(day);
    const counts = held?.components[name];
    if (!held || !counts) return { day, tone: "none", text: `${day} · no data` };
    up += counts.up;
    expected += held.expected;
    const share = counts.up / held.expected;
    const slow = counts.degraded / held.expected > 0.05;
    const tone = share >= 0.999 ? (slow ? "warn" : "ok") : share >= 0.99 ? "warn" : "down";
    return { day, tone, text: `${day} · ${(share * 100).toFixed(2)}% up` };
  });
  return { out, up, expected };
}

const percent = (up: number, expected: number) => {
  if (!expected) return "—";
  const value = (up / expected) * 100;
  return `${value >= 99.995 ? "100" : value.toFixed(2)}%`;
};

/** The eight buttons of the cabinet's ring, doing the job of the status light. */
function StatusRing({ tone }: { tone: string }) {
  const size = 168;
  const r = size / 2;
  const ringR = r * 0.78;
  return (
    <svg className={`ring status-ring ${tone}`} viewBox={`0 0 ${size} ${size}`} width={size} height={size} role="img" aria-label="Status light">
      <circle className="rim-edge" cx={r} cy={r} r={ringR} style={{ strokeWidth: 5 }} />
      <circle className="rim" cx={r} cy={r} r={ringR} style={{ strokeWidth: 3 }} />
      <circle className="screen" cx={r} cy={r} r={r * 0.46} />
      {Array.from({ length: 8 }, (_, i) => {
        const angle = ((-67.5 + i * 45) * Math.PI) / 180;
        return <circle key={i} className="btn" cx={(r + ringR * Math.cos(angle)).toFixed(1)} cy={(r + ringR * Math.sin(angle)).toFixed(1)} r={size * 0.075} style={{ animationDelay: `${i * 0.12}s` }} />;
      })}
    </svg>
  );
}

function Spark({ readings, pick, unit }: { readings: Reading[]; pick: (r: Reading) => number; unit: string }) {
  const W = 320;
  const H = 84;
  if (readings.length < 2) return <p className="hint">Not enough readings yet.</p>;
  const values = readings.map(pick);
  const top = Math.max(...values, 1);
  const first = new Date(readings[0].at).getTime();
  const span = new Date(readings[readings.length - 1].at).getTime() - first || 1;
  const xy = readings.map((r, i) => [((new Date(r.at).getTime() - first) / span) * W, H - 6 - (values[i] / top) * (H - 12)] as const);
  const line = xy.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  const last = values[values.length - 1];
  return (
    <>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${last}${unit} now, ${top}${unit} at most in the last day`} preserveAspectRatio="none">
        <polygon points={`0,${H} ${line} ${W},${H}`} className="fill" />
        <polyline points={line} className="trace" vectorEffect="non-scaling-stroke" />
      </svg>
      <p className="hint">
        <b>
          {last}
          {unit}
        </b>{" "}
        now · peak {top}
        {unit}
      </p>
    </>
  );
}

export default async function Page() {
  const site = siteUrl();
  const now: Snapshot = await snapshot();
  const overall: Word = now.ok ? now.status : "unreachable";
  const tone = WORDS[overall].tone;
  const say = HEADLINE[overall];
  const names = now.ok
    ? [...ORDER.filter((n) => n in now.components), ...Object.keys(now.components).filter((n) => !ORDER.includes(n))]
    : ORDER;
  const rows = names.map((name) => ({
    name,
    state: (now.ok ? (now.components[name] ?? "operational") : "unreachable") as Word,
    ...(now.ok ? cells(now.days, name) : { out: [], up: 0, expected: 0 }),
  }));
  const up = rows.reduce((sum, r) => sum + r.up, 0);
  const expected = rows.reduce((sum, r) => sum + r.expected, 0);

  return (
    <div className="wrap">
      <header className="top">
        <Ring lit={0} size={30} />
        <a className="wordmark" href={`${site}/`}>
          Ras<span>mai</span>
        </a>
        <span className="tag here">status</span>
        <a className="tag back" href={`${site}/`}>
          rasmai.lol ↗
        </a>
        <ThemeToggle />
      </header>

      <section className={`hero ${tone}`} aria-live="polite">
        <StatusRing tone={tone} />
        <div className="hero-text">
          <p className="tag">right now</p>
          <h1>
            {say.before}
            <em>{say.em}</em>
            {say.after}
          </h1>
          <p className="lede">{say.lede}</p>
        </div>
      </section>

      <ul className="vitals">
        <li>
          <span className="lbl">uptime · {DAYS}d</span>
          <b>{now.ok ? percent(up, expected) : "—"}</b>
        </li>
        <li>
          <span className="lbl">discord</span>
          <b>{now.ok && now.metrics.gatewayMs !== undefined ? `${now.metrics.gatewayMs} ms` : "—"}</b>
        </li>
        <li>
          <span className="lbl">waiting</span>
          <b>{now.ok && now.metrics.analysisWaiting !== undefined ? now.metrics.analysisWaiting : "—"}</b>
        </li>
      </ul>

      <h2 className="sect">Parts</h2>
      <ul className="ledger" aria-label="Parts">
        {rows.map((row) => (
          <li key={row.name} className={WORDS[row.state].tone}>
            <div className="who">
              <span className="lamp" aria-hidden />
              <div>
                <h3>{NAMES[row.name] ?? row.name}</h3>
                <span className="state">{WORDS[row.state].label}</span>
              </div>
            </div>
            <div className="bars" role="img" aria-label={`Last ${DAYS} days`}>
              {row.out.map((c) => (
                <i key={c.day} className={c.tone} title={c.text} />
              ))}
            </div>
            <span className="pct">{percent(row.up, row.expected)}</span>
          </li>
        ))}
      </ul>

      {now.ok ? (
        <>
          <h2 className="sect">Last 24 hours</h2>
          <section className="charts" aria-label="Last 24 hours">
            <div>
              <h3>Discord response time</h3>
              <Spark readings={now.recent} pick={(r) => r.gatewayMs} unit=" ms" />
            </div>
            <div>
              <h3>People waiting on a build</h3>
              <Spark readings={now.recent} pick={(r) => r.waiting} unit="" />
            </div>
          </section>
        </>
      ) : null}

      <p className="hint note">Checked every 5 minutes. A gap in the record counts as down. This page refreshes itself every minute.</p>

      <footer className="foot">
        <span>
          Created by <b>nek_ng</b> · not affiliated with SEGA
        </span>
        <span>
          <a href={`${site}/privacy/`}>privacy</a> · <a href={`${site}/terms/`}>terms</a>
        </span>
      </footer>
    </div>
  );
}
