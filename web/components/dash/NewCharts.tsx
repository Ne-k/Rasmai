import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { useLocale } from "@/components/I18n";
import { traitName } from "@/lib/i18n/traits";
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

const MODES = ["easy", "balanced", "hard", "extreme"];
const DIFFS = [
  { key: "any", label: "" },
  { key: "remaster", label: "Re:MASTER" },
  { key: "master", label: "MASTER" },
  { key: "expert", label: "EXPERT" },
  { key: "advanced", label: "ADVANCED" },
  { key: "basic", label: "BASIC" },
];

export function NewCharts({ initialChallenge, initialDifficulty, onOpen }: { initialChallenge: string; initialDifficulty: string; onOpen?: OpenChart }) {
  const t = useTranslations("newTab");
  const c = useTranslations("cols");
  const ch = useTranslations("challenge");
  const p = useTranslations("picksTab");
  const list = useTranslations("list");
  const common = useTranslations("common");
  const locale = useLocale();
  const [challenge, setChallenge] = useState(MODES.includes(initialChallenge) ? initialChallenge : "balanced");
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

  const mode = { label: ch(`label.${challenge}` as never), note: ch(`newNote.${challenge}` as never) };
  return (
    <>
      <div className="row-between">
        <div className="seg" role="group" aria-label={t("howHard")}>
          {MODES.map((l) => (
            <button key={l} type="button" className={l === challenge ? "on" : ""} aria-pressed={l === challenge} onClick={() => setChallenge(l)}>
              {ch(`label.${l}` as never)}
            </button>
          ))}
        </div>
        <div className="filters" style={{ margin: 0 }}>
          <select value={difficulty} onChange={(e) => setDifficulty(e.target.value)} aria-label={t("difficulty")}>
            {DIFFS.map((d) => (
              <option key={d.key} value={d.key}>
                {d.label || t("expertUp")}
              </option>
            ))}
          </select>
          <select value={level} onChange={(e) => setLevel(e.target.value)} aria-label={t("level")}>
            {LEVELS.map((lv) => (
              <option key={lv} value={lv}>
                {lv === "any" ? p("anyLevel") : p("level", { l: lv })}
              </option>
            ))}
          </select>
          <select value={focus} onChange={(e) => setFocus(e.target.value)} aria-label={t("lean")}>
            <option value="none">{t("anyTrait")}</option>
            <option value="weak">{t("weak")}</option>
            <option value="strong">{t("strong")}</option>
          </select>
        </div>
      </div>
      {current && current.focus !== "none" && current.traits.length > 0 && (
        <p className="hint" style={{ marginTop: 10 }}>
          {t("leaning", { weak: String(current.focus === "weak") })}
          {current.traits.map((x) => `${traitName(x.label, undefined, locale)} (${x.offset > 0 ? "+" : ""}${x.offset.toFixed(2)})`).join(list("sep"))}{common("period")}
        </p>
      )}
      <p className="hint" style={{ marginTop: 10 }}>
        {level === "any"
          ? t("anyNote", { note: mode.note })
          : t("levelNote", { level, mode: mode.label })}
      </p>
      {error && <LoadError what={t("theNew")} message={error} onRetry={() => setError("")} />}
      {!current && !error && <Empty>{t("looking")}</Empty>}
      {current && (
        <section className="ledger">
          <div className="ledger-head">
            <Label info={t("headInfo")}>
              {t("head", { n: current.picks.length, level: current.level, from: current.window[0].toFixed(1), to: current.window[1].toFixed(1) })}
            </Label>
            <span className="mono hint">{t("sorted", { mode: mode.label })}</span>
          </div>
          {current.picks.length === 0 ? (
            <Empty>{current.level !== "any" ? t("allPlayed", { level: current.level }) : t("noneHere")}{t("tryAnother")}</Empty>
          ) : (
            <div className="scroll">
            <table className="tbl">
              <thead>
                <tr>
                  <th className="c-n">#</th>
                  <th colSpan={2}>{c("chart")}</th>
                  <th>{c("genre")}</th>
                  <th className="c-num">{c("constant")}</th>
                  <th className="c-num">{c("firstPass")}</th>
                  <th className="c-num">{c("oddsS")}</th>
                  <th className="c-num">{c("worth")}</th>
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
                      {n.is_new && <span className="tag-b50">{t("thisVersion")}</span>}
                    </td>
                    <td className="dim" data-l={c("genre")}>{n.genre}</td>
                    <td className="c-num mono" data-l={c("constant")}>{n.constant.toFixed(1)}</td>
                    <td className="c-num mono strong" data-l={c("firstPass")}>
                      ~{pct(n.expected_accuracy, 1)} {n.expected_rank}
                    </td>
                    <td className="c-num mono" data-l={c("oddsS")}>{Math.round(n.odds_of_s * 100)}%</td>
                    <td className="c-num mono gain" data-l={c("worth")}>{n.rating_gain > 0 ? `+${n.rating_gain}` : <span className="dim">{t("banks", { n: n.expected_rating })}</span>}</td>
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
