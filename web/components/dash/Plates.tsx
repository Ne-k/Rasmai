import { useEffect, useRef, useState } from "react";
import { getJSON } from "./api";
import { Chip, Empty, Jacket, Label, LoadError, TitleLink, type OpenChart } from "./bits";

type PlateGoal = { goal: string; label: string; title: string; required: number; met: number };
type PlateEntry = { key: string; name: string; reading: string; required: number; played: number; goals: PlateGoal[] };
type PlateChart = {
  title: string;
  type: string;
  difficulty: string;
  level: string;
  constant: number;
  cover: string;
  played: boolean;
  need: string;
};
type PlateDetail = { key: string; name: string; reading: string; title: string; goal: string; label: string; required: number; met: number; missing: PlateChart[] };

// the list grows in steps: Mai alone can be two thousand charts
const STEP = 60;

function Bar({ goal, on, onPick }: { goal: PlateGoal; on: boolean; onPick: () => void }) {
  const share = goal.required ? Math.min(100, (100 * goal.met) / goal.required) : 0;
  const done = goal.required > 0 && goal.met >= goal.required;
  return (
    <button type="button" className={`plate-goal g-${goal.label.toLowerCase()}${done ? " done" : ""}${on ? " on" : ""}`} onClick={onPick}
            aria-pressed={on} title={`${goal.title || goal.label}: ${goal.met} of ${goal.required}`}>
      <span className="k">{goal.label}</span>
      <span className="bar">
        <span style={{ width: `${share}%` }} />
      </span>
      <span className="mono n">{done ? "done" : `${goal.met}/${goal.required}`}</span>
    </button>
  );
}

function Missing({ plate, goal, onOpen }: { plate: string; goal: string; onOpen?: OpenChart }) {
  const [data, setData] = useState<PlateDetail | null>(null);
  const [error, setError] = useState("");
  const [shown, setShown] = useState(STEP);
  const box = useRef<HTMLElement>(null);
  useEffect(() => {
    setData(null);
    setError("");
    setShown(STEP);
    getJSON<PlateDetail>(`/api/me/plates?plate=${encodeURIComponent(plate)}&goal=${encodeURIComponent(goal)}`)
      .then(setData)
      .catch((e: Error) => setError(e.message));
  }, [plate, goal]);
  // the list sits under every tile, so the bar that asked for it brings it into view
  useEffect(() => {
    if (data) box.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [data]);
  if (error) return <LoadError what="that plate" message={error} />;
  if (!data) return <Empty>Checking every chart…</Empty>;
  const title = data.title ? `${data.title} · ${data.name}` : `${data.name} ${data.label}`;
  return (
    <section className="ledger plate-detail" ref={box}>
      <div className="ledger-head">
        <Label>
          {title}
        </Label>
        <span className="mono hint">
          {data.met}/{data.required} at {data.label} · {data.missing.length} to go
        </span>
      </div>
      {data.missing.length === 0 ? (
        <Empty>Every chart is there. The plate is yours.</Empty>
      ) : (
        <>
          <ul className="plate-missing">
            {data.missing.slice(0, shown).map((c) => (
              <li key={`${c.title}|${c.type}|${c.difficulty}`}>
                <Jacket cover={c.cover} size={36} />
                <span className="plate-chart">
                  <TitleLink title={c.title} type={c.type} difficulty={c.difficulty} onOpen={onOpen} />
                  <Chip difficulty={c.difficulty} level={c.level} constant={c.constant} type={c.type} />
                </span>
                <span className={`mono need${c.played ? "" : " dim"}`}>{c.need}</span>
              </li>
            ))}
          </ul>
          {data.missing.length > shown && (
            <button type="button" className="linkish" onClick={() => setShown((n) => n + STEP)}>
              show {Math.min(STEP, data.missing.length - shown)} more of {data.missing.length - shown}
            </button>
          )}
        </>
      )}
    </section>
  );
}

/** Version plates: a tile per plate with a bar per condition; a bar opens the charts that plate still needs. */
export function Plates({ onOpen }: { onOpen?: OpenChart }) {
  const [plates, setPlates] = useState<PlateEntry[] | null>(null);
  const [error, setError] = useState("");
  const [reload, setReload] = useState(0);
  const [pick, setPick] = useState<{ plate: string; goal: string } | null>(null);
  useEffect(() => {
    getJSON<{ plates: PlateEntry[] }>("/api/me/plates")
      .then((d) => setPlates(d.plates))
      .catch((e: Error) => setError(e.message));
  }, [reload]);
  if (error) return <LoadError what="your plates" message={error} onRetry={() => { setError(""); setReload((n) => n + 1); }} />;
  if (!plates) return <Empty>Checking every chart…</Empty>;
  if (!plates.length) return <Empty>No scores read yet. A read from the Account tab or any Discord command brings them in.</Empty>;
  return (
    <>
      <section className="ledger">
        <div className="ledger-head">
          <Label info="You earn a plate by meeting one condition on every chart of a version, BASIC to MASTER. Mai covers every standard chart up to FiNALE, Re:MASTER included, and has a Clear plate too. Pick a bar to see what is left.">
            version plates
          </Label>
          <span className="mono hint">FC · SSS 100% · AP · FDX · Clear 80%</span>
        </div>
        <ul className="plates">
          {plates.map((p) => (
            <li key={p.key} className="plate">
              <span className={`plate-chip${p.key === p.name ? " word" : ""}`}>{p.key}</span>
              <span className="plate-name">
                {p.reading ? `${p.reading} · ${p.name}` : p.name}
                <small className="mono">{p.required} charts · {p.played} played</small>
              </span>
              <span className="plate-goals">
                {p.goals.map((g) => (
                  <Bar key={g.goal} goal={g} on={pick?.plate === p.key && pick.goal === g.goal} onPick={() => setPick({ plate: p.key, goal: g.goal })} />
                ))}
              </span>
            </li>
          ))}
        </ul>
      </section>
      {pick && <Missing plate={pick.plate} goal={pick.goal} onOpen={onOpen} />}
    </>
  );
}
