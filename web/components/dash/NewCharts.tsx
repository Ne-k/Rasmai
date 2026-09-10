import { useEffect, useState } from "react";
import { getJSON, type NewPick } from "./api";
import { Chip, Empty, Jacket, Label, LoadError, pct } from "./bits";
import { TitleLink, type OpenChart } from "./bits";

type NewData = {
  challenge: string;
  label: string;
  difficulty: string;
  level: string;
  focus: string;
  traits: { label: string; offset: number; count: number }[];
  window: [number, number];
  picks: NewPick[];
};

const LEVELS = ["any", "15", "14+", "14", "13+", "13", "12+", "12", "11+", "11", "10+", "10", "9+", "9", "8+", "8", "7+"];

const MODES = [
  { key: "easy", label: "Easier", note: "charts you will almost certainly S, from where you are comfortable" },
  { key: "balanced", label: "Balanced", note: "best value just under your S reach" },
  { key: "hard", label: "Challenging", note: "the hardest charts where an S is still within reach" },
  { key: "extreme", label: "Long shots", note: "past your ceiling, where a first pass is a gamble" },
];
const DIFFS = [
  { key: "any", label: "Expert and up" },
  { key: "remaster", label: "Re:MASTER" },
  { key: "master", label: "MASTER" },
  { key: "expert", label: "EXPERT" },
  { key: "advanced", label: "ADVANCED" },
  { key: "basic", label: "BASIC" },
];

export function NewCharts({ initialChallenge, initialDifficulty, onOpen }: { initialChallenge: string; initialDifficulty: string; onOpen?: OpenChart }) {
  const [challenge, setChallenge] = useState(MODES.some((l) => l.key === initialChallenge) ? initialChallenge : "balanced");
  const [difficulty, setDifficulty] = useState(DIFFS.some((d) => d.key === initialDifficulty) ? initialDifficulty : "any");
  const [level, setLevel] = useState("any");
  const [focus, setFocus] = useState("none");
  const [data, setData] = useState<Record<string, NewData>>({});
  const [error, setError] = useState("");
  const key = `${challenge}|${difficulty}|${level}|${focus}`;
  const current = data[key];

  useEffect(() => {
    if (data[key] || error) return;
    const query = `challenge=${challenge}&difficulty=${difficulty}${level !== "any" ? `&level=${encodeURIComponent(level)}` : ""}${focus !== "none" ? `&focus=${focus}` : ""}`;
    getJSON<NewData>(`/api/me/new?${query}`)
      .then((d) => setData((prev) => ({ ...prev, [key]: d })))
      .catch((e: Error) => setError(e.message));
  }, [key, challenge, difficulty, level, focus, data]);

  const mode = MODES.find((l) => l.key === challenge)!;
  return (
    <>
      <div className="row-between">
        <div className="seg" role="group" aria-label="How far above your usual scores to look">
          {MODES.map((l) => (
            <button key={l.key} type="button" className={l.key === challenge ? "on" : ""} aria-pressed={l.key === challenge} onClick={() => setChallenge(l.key)}>
              {l.label}
            </button>
          ))}
        </div>
        <div className="filters" style={{ margin: 0 }}>
          <select value={difficulty} onChange={(e) => setDifficulty(e.target.value)} aria-label="Difficulty">
            {DIFFS.map((d) => (
              <option key={d.key} value={d.key}>
                {d.label}
              </option>
            ))}
          </select>
          <select value={level} onChange={(e) => setLevel(e.target.value)} aria-label="Level">
            {LEVELS.map((lv) => (
              <option key={lv} value={lv}>
                {lv === "any" ? "any level" : `level ${lv}`}
              </option>
            ))}
          </select>
          <select value={focus} onChange={(e) => setFocus(e.target.value)} aria-label="Lean toward a trait">
            <option value="none">any trait</option>
            <option value="weak">what you struggle with</option>
            <option value="strong">what you excel at</option>
          </select>
        </div>
      </div>
      {current && current.focus !== "none" && current.traits.length > 0 && (
        <p className="hint" style={{ marginTop: 10 }}>
          Leaning toward {current.focus === "weak" ? "what you struggle with" : "what you excel at"}:{" "}
          {current.traits.map((t) => `${t.label} (${t.offset > 0 ? "+" : ""}${t.offset.toFixed(2)})`).join(", ")}.
        </p>
      )}
      <p className="hint" style={{ marginTop: 10 }}>
        {level === "any"
          ? `${mode.note}. Charts you have never played on this account, in the constant window the level searches. The estimate is a first pass: a little under where you usually land at that constant.`
          : `Every level ${level} chart you have never played on this account, ordered the way the ${mode.label.toLowerCase()} level ranks them. The estimate is a first pass: a little under where you usually land at that constant.`}
      </p>
      {error && <LoadError what="the new charts" message={error} onRetry={() => setError("")} />}
      {!current && !error && <Empty>Looking for charts…</Empty>}
      {current && (
        <section className="ledger">
          <div className="ledger-head">
            <Label info="Every chart you have never played on this account in this window, ordered the way the chosen level ranks them. First pass is the score the model expects the first time you play it, Odds of S is how likely an S is, and Worth is what an S would add to your rating.">
              {current.picks.length} charts · {current.level !== "any" ? `level ${current.level} · ` : ""}constants {current.window[0].toFixed(1)}–{current.window[1].toFixed(1)}
            </Label>
            <span className="mono hint">sorted the way this level ranks them</span>
          </div>
          {current.picks.length === 0 ? (
            <Empty>{current.level !== "any" ? `Every level ${current.level} chart at this difficulty has been played already, or none exists.` : "Nothing unplayed fits this window."} Try another level or difficulty.</Empty>
          ) : (
            <div className="scroll">
            <table className="tbl">
              <thead>
                <tr>
                  <th className="c-n">#</th>
                  <th colSpan={2}>Chart</th>
                  <th>Genre</th>
                  <th className="c-num">Const</th>
                  <th className="c-num">First pass</th>
                  <th className="c-num">Odds of S</th>
                  <th className="c-num">Worth</th>
                </tr>
              </thead>
              <tbody>
                {current.picks.map((n, i) => (
                  <tr key={`${n.title}|${n.chart_type}|${n.difficulty}`}>
                    <td className="c-n">{i + 1}</td>
                    <td className="c-jacket">
                      <Jacket cover={n.cover} />
                    </td>
                    <td className="c-title">
                      <TitleLink title={n.title} type={n.chart_type} difficulty={n.difficulty} onOpen={onOpen} />
                      <Chip difficulty={n.difficulty} level={n.level} constant={n.constant} type={n.chart_type} />
                      {n.is_new && <span className="tag-b50">this version</span>}
                    </td>
                    <td className="dim" data-l="genre">{n.genre}</td>
                    <td className="c-num mono" data-l="const">{n.constant.toFixed(1)}</td>
                    <td className="c-num mono strong" data-l="first pass">
                      ~{pct(n.expected_accuracy, 1)} {n.expected_rank}
                    </td>
                    <td className="c-num mono" data-l="odds of S">{Math.round(n.odds_of_s * 100)}%</td>
                    <td className="c-num mono gain" data-l="worth">{n.rating_gain > 0 ? `+${n.rating_gain}` : <span className="dim">banks {n.expected_rating}</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            </div>
          )}
        </section>
      )}
    </>
  );
}
