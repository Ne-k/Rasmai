import { useEffect, useRef, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { getJSON } from "./api";
import { Chip, Empty, Jacket, Label, LoadError, TitleLink, type OpenChart } from "./bits";
import { PlateArt } from "./PlateArt";

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
  accuracy: number | null;
  fc: string;
  fs: string;
  chance: number | null;
  band: string;
};
type PlateDetail = {
  key: string; name: string; reading: string; hue: [string, string] | null; title: string; goal: string; label: string;
  required: number; met: number; missing: PlateChart[]; odds: boolean;
};
type Order = "likely" | "unlikely";

// a chance as a percentage that never claims certainty, as the bot prints it (chance_text in rasmai/engine/plates.py)
const chanceText = (p: number) => (p < 0.005 ? "<1%" : p > 0.995 ? ">99%" : `${Math.round(p * 100)}%`);

// the list grows in steps: Mai alone can be two thousand charts
const STEP = 60;

function usePlateName() {
  const t = useTranslations("platesTab");
  const english = useLocale() !== "ja";
  // Japanese players name a plate by its kanji, which the chip already shows; the English reading is for everyone else
  return (p: { key: string; name: string; reading: string }) => {
    const name = p.key === "舞" ? t("maiName") : p.name;
    return english && p.reading ? `${p.reading} · ${name}` : name;
  };
}

function Bar({ goal, on, onPick }: { goal: PlateGoal; on: boolean; onPick: () => void }) {
  const t = useTranslations("platesTab");
  const share = goal.required ? Math.min(100, (100 * goal.met) / goal.required) : 0;
  const done = goal.required > 0 && goal.met >= goal.required;
  return (
    <button type="button" className={`plate-goal g-${goal.label.toLowerCase()}${done ? " done" : ""}${on ? " on" : ""}`} onClick={onPick}
            aria-pressed={on} title={t("barTitle", { name: goal.title || goal.label, met: goal.met, required: goal.required })}>
      <span className="k">{goal.label}</span>
      <span className="bar">
        <span style={{ width: `${share}%` }} />
      </span>
      <span className="mono n">{done ? t("done") : `${goal.met}/${goal.required}`}</span>
    </button>
  );
}

function Missing({ plate, goal, onOpen }: { plate: string; goal: string; onOpen?: OpenChart }) {
  const t = useTranslations("platesTab");
  const plateName = usePlateName();
  const [data, setData] = useState<PlateDetail | null>(null);
  const [error, setError] = useState("");
  const [shown, setShown] = useState(STEP);
  const [order, setOrder] = useState<Order>("likely");
  const box = useRef<HTMLElement>(null);
  const opened = useRef("");
  useEffect(() => {
    // an answer to a request a later click replaced is dropped, so the list always matches the switch
    let live = true;
    setError("");
    setShown(STEP);
    getJSON<PlateDetail>(`/api/me/plates?plate=${encodeURIComponent(plate)}&goal=${encodeURIComponent(goal)}&order=${order}`)
      .then((d) => live && setData(d))
      .catch((e: Error) => live && setError(e.message));
    return () => {
      live = false;
    };
  }, [plate, goal, order]);
  // the list sits under every tile, so the bar that asked for it brings it into view; a re-sort leaves the page where it is
  useEffect(() => {
    if (!data || opened.current === `${plate}|${goal}`) return;
    opened.current = `${plate}|${goal}`;
    box.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [data, plate, goal]);
  if (error) return <LoadError what={t("thatPlate")} message={error} />;
  if (!data || data.key !== plate || data.goal !== goal) return <Empty>{t("loading")}</Empty>;
  // what a chart still lacks: its score for Clear and SSS, its lamp for the others
  const need = (c: PlateChart) => {
    if (!c.played) return t("unplayed");
    if (goal === "覇者" || goal === "将") return `${(c.accuracy ?? 0).toFixed(2)}% → ${data.label}`;
    const lamp = (goal === "舞舞" ? c.fs : c.fc).toUpperCase();
    return !lamp || lamp === "NONE" || lamp === "SYNC" ? t("noLamp", { label: data.label }) : `${lamp} → ${data.label}`;
  };
  return (
    <section className="ledger plate-detail" ref={box}>
      <div className="ledger-head">
        <Label>
          {plateName(data)} · {data.label}
        </Label>
        <span className="mono hint">{t("detailHint", { met: data.met, required: data.required, label: data.label, left: data.missing.length })}</span>
      </div>
      <div className="plate-art">
        <PlateArt plateKey={data.key} name={data.key === "舞" ? t("maiName") : data.name} goal={data.goal} label={data.label} hue={data.hue}
                  earned={data.met >= data.required} caption={t("artCaption", { label: data.label, required: data.required })} />
      </div>
      {data.missing.length === 0 ? (
        <Empty>{t("yours")}</Empty>
      ) : (
        <>
          {data.odds && (
            <div className="plate-sort">
              <span className="mono hint">{t("chanceInfo", { label: data.label })}</span>
              <span className="seg-toggle" role="group" aria-label={t("sort")}>
                {(["likely", "unlikely"] as Order[]).map((o) => (
                  <button key={o} type="button" aria-pressed={order === o} className={order === o ? "on" : ""} onClick={() => setOrder(o)}>
                    {t(o === "likely" ? "sortLikely" : "sortUnlikely")}
                  </button>
                ))}
              </span>
            </div>
          )}
          <ul className="plate-missing">
            {data.missing.slice(0, shown).map((c) => (
              <li key={`${c.title}|${c.type}|${c.difficulty}`}>
                <Jacket cover={c.cover} size={36} />
                <span className="plate-chart">
                  <TitleLink title={c.title} type={c.type} difficulty={c.difficulty} onOpen={onOpen} />
                  <Chip difficulty={c.difficulty} level={c.level} constant={c.constant} type={c.type} />
                </span>
                <span className={`mono need${c.played ? "" : " dim"}`}>{need(c)}</span>
                {c.chance !== null && (
                  <span className={`chance ${c.band}`} title={t("chanceTitle", { label: data.label })}>
                    <span className="meter" aria-hidden><span style={{ width: `${Math.round(c.chance * 100)}%` }} /></span>
                    <b className="mono">{chanceText(c.chance)}</b>
                  </span>
                )}
              </li>
            ))}
          </ul>
          {data.missing.length > shown && (
            <button type="button" className="linkish" onClick={() => setShown((n) => n + STEP)}>
              {t("more", { n: Math.min(STEP, data.missing.length - shown), left: data.missing.length - shown })}
            </button>
          )}
        </>
      )}
    </section>
  );
}

/** Version plates: a tile per plate with a bar per condition; a bar opens the charts that plate still needs. */
export function Plates({ onOpen }: { onOpen?: OpenChart }) {
  const t = useTranslations("platesTab");
  const plateName = usePlateName();
  const [plates, setPlates] = useState<PlateEntry[] | null>(null);
  const [error, setError] = useState("");
  const [reload, setReload] = useState(0);
  const [pick, setPick] = useState<{ plate: string; goal: string } | null>(null);
  useEffect(() => {
    getJSON<{ plates: PlateEntry[] }>("/api/me/plates")
      .then((d) => setPlates(d.plates))
      .catch((e: Error) => setError(e.message));
  }, [reload]);
  if (error) return <LoadError what={t("yourPlates")} message={error} onRetry={() => { setError(""); setReload((n) => n + 1); }} />;
  if (!plates) return <Empty>{t("loading")}</Empty>;
  if (!plates.length) return <Empty>{t("none")}</Empty>;
  return (
    <>
      <section className="ledger">
        <div className="ledger-head">
          <Label info={t("info")}>{t("label")}</Label>
          <span className="mono hint">{t("legend")}</span>
        </div>
        <ul className="plates">
          {plates.map((p) => (
            <li key={p.key} className="plate">
              <span className={`plate-chip${p.key === p.name ? " word" : ""}`}>{p.key}</span>
              <span className="plate-name">
                {plateName(p)}
                <small className="mono">{t("charts", { required: p.required, played: p.played })}</small>
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
