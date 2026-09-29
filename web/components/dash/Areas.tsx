import { useEffect, useState } from "react";
import { getJSON, type AreaSummary, type AreaEntry, type AreaReward } from "./api";
import { Empty, Label, LoadError, ago, day, num } from "./bits";

function km(value: number | null | undefined): string {
  return value === null || value === undefined ? "—" : `${num(value)} km`;
}

function endsIn(iso: string | null): string {
  if (!iso) return "";
  const end = new Date(iso).getTime();
  if (Number.isNaN(end)) return "";
  const days = Math.round((end - Date.now()) / 86400000);
  if (days < 0) return `ended ${day(iso)}`;
  if (days === 0) return "ends today";
  if (days === 1) return "ends tomorrow";
  return `ends in ${days} days · ${day(iso)}`;
}

function Reward({ step }: { step: AreaReward }) {
  if (!step.kind && !step.name) return null;
  return (
    <b>
      {step.kind ? <em>{step.kind}</em> : null}
      {step.name}
    </b>
  );
}

/** The dark panel of a card: the distance, and what the next reward is and how far it sits. */
function Panel({ area }: { area: AreaEntry }) {
  const travelling = area.state === "in_progress";
  const next = area.nextReward;
  const width = next && next.total > 0 ? Math.max(0, Math.min(100, (100 * area.distance) / next.total)) : area.state === "completed" ? 100 : 0;
  let reward: React.ReactNode = null;
  if (travelling && next) {
    const when =
      next.toGo === 0
        ? "ready to collect"
        : `${km(next.toGo)} to go${next.playsToGo !== null ? ` · about ${next.playsToGo} play${next.playsToGo === 1 ? "" : "s"} at your pace` : ""}`;
    reward = (
      <div className="area-next">
        <span className="lbl">next reward</span>
        <Reward step={next} />
        <span className="w">{when}</span>
      </div>
    );
  } else if (travelling) {
    reward = (
      <div className="area-next">
        <span className="lbl">next reward</span>
        <span className="w">not listed for this area</span>
      </div>
    );
  } else if (area.state === "completed") {
    reward = (
      <div className="area-next done">
        <span className="lbl">completed</span>
        <span className="w">every reward collected</span>
      </div>
    );
  } else {
    reward = (
      <div className="area-next gift">
        <span className="lbl">first play</span>
        {area.firstGift ? <Reward step={area.firstGift} /> : <span className="w">you get a gift</span>}
      </div>
    );
  }
  return (
    <div className="area-panel">
      <div className="area-dist">
        <span className="lbl">total distance</span>
        <b>
          {num(area.distance)}
          <small>km</small>
        </b>
      </div>
      {reward}
      {((travelling && next && next.total > 0) || area.state === "completed") && (
        <span className="bar">
          <span style={{ width: `${width}%` }} />
        </span>
      )}
    </div>
  );
}

/** The artwork strip across the top of a card. A banner fills it; square art sits over a blurred copy of itself. */
function Art({ area }: { area: AreaEntry }) {
  const [shape, setShape] = useState("");
  if (!area.imageKey) return <div className="area-art-wrap empty" />;
  const src = `/api/area-image/${area.imageKey}`;
  return (
    <div className={`area-art-wrap ${shape}`}>
      <img className="area-art-bg" src={src} alt="" aria-hidden="true" loading="lazy" width={300} height={150} />
      <img
        className="area-art"
        src={src}
        alt=""
        loading="lazy"
        width={300}
        height={150}
        onLoad={(e) => setShape(e.currentTarget.naturalWidth >= e.currentTarget.naturalHeight * 1.5 ? "wide" : "tall")}
      />
    </div>
  );
}

function slug(name: string): string {
  return `area-${encodeURIComponent(name).replace(/%/g, "_")}`;
}

function AreaCard({ area, focused }: { area: AreaEntry; focused?: boolean }) {
  const english = area.english && area.english.toLowerCase() !== area.name.toLowerCase() ? area.english : "";
  const notes: string[] = [];
  if (area.gained > 0 && area.since) notes.push(`+${km(area.gained)} since ${day(area.since)}`);
  if (area.pace && area.state === "in_progress") notes.push(`${area.pace} km per play${area.ownPace ? "" : ", based on your other areas"}`);
  const period = endsIn(area.periodEnd);
  if (period) notes.push(period);
  const later = area.nextRewards.filter((step) => !area.nextReward || step.total !== area.nextReward.total).slice(0, 2);
  return (
    <li className={`area ${area.state}${focused ? " focus" : ""}`} id={slug(area.name)}>
      <Art area={area} />
      <div className="area-body">
        <div className="area-head">
          <span className="area-pill">{area.name}</span>
          <span className={`area-state ${area.state}`}>{area.stateLabel}</span>
        </div>
        {english ? <span className="area-english">{english}</span> : null}
        <Panel area={area} />
        {notes.length > 0 && <p className="hint">{notes.join(" · ")}</p>}
        {later.length > 0 && (
          <ul className="area-rewards">
            {later.map((step) => (
              <li key={step.total}>
                <span className="mono">{num(step.total)} km</span> {step.kind}
                {step.name ? <b> {step.name}</b> : null}
                {step.playsToGo !== null ? <span className="dim"> · ~{step.playsToGo} plays</span> : null}
              </li>
            ))}
          </ul>
        )}
      </div>
    </li>
  );
}

function CompactRow({ area, right, focused }: { area: AreaEntry; right?: React.ReactNode; focused?: boolean }) {
  return (
    <li className={`area ${area.state}${focused ? " focus" : ""}`} id={slug(area.name)}>
      <span className="area-name">
        {area.name}
        {area.english ? <span className="area-english">{area.english}</span> : null}
      </span>
      {right}
    </li>
  );
}

export function Areas({ focus = "" }: { focus?: string }) {
  const [data, setData] = useState<AreaSummary | null>(null);
  const [error, setError] = useState("");
  const [reload, setReload] = useState(0);
  useEffect(() => {
    getJSON<AreaSummary>("/api/me/areas")
      .then(setData)
      .catch((e: Error) => setError(e.message));
  }, [reload]);
  // a link from Discord names one area: bring its card into view once the list is there
  useEffect(() => {
    if (!focus || !data) return;
    const card = document.getElementById(slug(focus));
    if (card) card.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [focus, data]);
  if (error) return <LoadError what="your areas" message={error} onRetry={() => { setError(""); setData(null); setReload((n) => n + 1); }} />;
  if (!data) return <Empty>Loading areas…</Empty>;
  const all = [...data.areas, ...data.events, ...(data.ended ?? [])];
  if (!all.length) {
    return <Empty>No area data yet. Hit refresh on the Account tab or run any command in Discord.</Empty>;
  }
  const travelling = data.areas.filter((a) => a.state === "in_progress");
  const done = data.areas.filter((a) => a.state === "completed");
  const untouched = data.areas.filter((a) => a.state === "not_started");
  const liveEvents = data.events.filter((a) => a.state !== "not_started");
  const waitingEvents = data.events.filter((a) => a.state === "not_started");
  return (
    <>
      <section className="ledger">
        <div className="ledger-head">
          <Label info="Every play moves you further in your current area, and rewards unlock at set distances. This is from your last refresh.">area travel</Label>
          <span className="mono hint">{data.readAt ? `updated ${ago(data.readAt)}` : "from your last refresh"}</span>
        </div>
        <dl className="facts">
          <dt>under way</dt>
          <dd className="mono">{data.counts.travelling}</dd>
          <dt>completed</dt>
          <dd className="mono">{data.counts.completed}</dd>
          <dt>not started</dt>
          <dd className="mono">{data.counts.untouched}</dd>
          <dt>distance per play</dt>
          <dd className="mono">{data.pace ? `${data.pace} km · from ${data.readings} reading${data.readings === 1 ? "" : "s"}` : "not measured yet"}</dd>
        </dl>
        <p className="hint">
          maimai DX NET only shows total distance, so plays left shows up once your distance changes between two refreshes. Area names are from SilentBlue RemyWiki.
        </p>
      </section>
      {travelling.length > 0 && (
        <section className="ledger">
          <div className="ledger-head">
            <Label info="Areas you're partway through, with the distance and plays left to the next reward.">in progress</Label>
          </div>
          <ul className="areas">
            {travelling.map((a) => (
              <AreaCard key={`area:${a.name}`} area={a} focused={a.name === focus} />
            ))}
          </ul>
        </section>
      )}
      {liveEvents.length > 0 && (
        <section className="ledger">
          <div className="ledger-head">
            <Label info="Limited-time areas. You can only get their rewards while they're running.">event areas</Label>
          </div>
          <ul className="areas">
            {liveEvents.map((a) => (
              <AreaCard key={`event:${a.name}`} area={a} focused={a.name === focus} />
            ))}
          </ul>
        </section>
      )}
      {untouched.length > 0 && (
        <section className="ledger">
          <div className="ledger-head">
            <Label info="Areas you haven't started. Pick one on the cab and play once to get its first gift.">not started · {untouched.length}</Label>
            <span className="mono hint">the first play in each gives a gift</span>
          </div>
          <ul className="areas">
            {untouched.map((a) => (
              <AreaCard key={`area:${a.name}`} area={a} focused={a.name === focus} />
            ))}
          </ul>
        </section>
      )}
      {waitingEvents.length > 0 && (
        <section className="ledger">
          <div className="ledger-head">
            <Label info="Event areas you haven't started and when each one ends.">events not started</Label>
          </div>
          <ul className="areas compact">
            {waitingEvents.map((a) => (
              <CompactRow key={`event:${a.name}`} area={a} focused={a.name === focus} right={<span className="hint">{endsIn(a.periodEnd)}</span>} />
            ))}
          </ul>
        </section>
      )}
      {(data.ended ?? []).length > 0 && (
        <section className="ledger">
          <div className="ledger-head">
            <Label info="Events that are over. maimai DX NET doesn't show your distance for these anymore.">ended events · {data.ended.length}</Label>
            <span className="mono hint">names and dates only</span>
          </div>
          <ul className="areas compact ended">
            {data.ended.map((a) => (
              <li key={`ended:${a.name}`} className="area ended">
                {a.imageKey ? <img className="area-banner" src={`/api/area-image/${a.imageKey}`} alt="" loading="lazy" width={92} height={46} /> : null}
                <span className="area-name">
                  {a.name}
                  {a.english ? <span className="area-english">{a.english}</span> : null}
                </span>
                <span className="mono dim">
                  {day(a.periodStart)}, {day(a.periodEnd)}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}
      {done.length > 0 && (
        <section className="ledger">
          <div className="ledger-head">
            <Label info="Areas you've finished and the distance each one took.">completed · {done.length}</Label>
          </div>
          <ul className="areas compact">
            {done.map((a) => (
              <CompactRow key={`area:${a.name}`} area={a} focused={a.name === focus} right={<span className="mono dim">{km(a.distance)}</span>} />
            ))}
          </ul>
        </section>
      )}
    </>
  );
}
