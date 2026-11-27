import type { CSSProperties } from "react";

const GOAL_CLASSES: Record<string, string> = { 覇者: "clear", 極: "fc", 将: "sss", 神: "ap", 舞舞: "fdx" };

/** Rasmai's nameplate for one plate and condition, as the bot's images draw it (plate_art in rasmai/images/pages/plates.py). */
export function PlateArt({ plateKey, name, goal, label, hue, earned, caption }: {
  plateKey: string;
  name: string;
  goal: string;
  label: string;
  hue: [string, string] | null;
  earned: boolean;
  caption: string;
}) {
  const kanji = plateKey.length === 1 ? plateKey : "";
  const title = goal === "覇者" ? "覇者" : kanji ? `${kanji}${goal}` : label;
  const [first, second] = hue ?? ["#ff3d8f", "#f0c04a"];
  return (
    <div className={`pa g-${GOAL_CLASSES[goal] ?? "fc"}${earned ? "" : " locked"}`} style={{ "--p1": first, "--p2": second } as CSSProperties}
         role="img" aria-label={`${title} · ${name} · ${caption}`}>
      <span className={`pa-chip${kanji ? "" : " word"}`} aria-hidden>{kanji || plateKey}</span>
      <span className="pa-mid" aria-hidden>
        <b>{name}</b>
        <small>{caption}</small>
      </span>
      <span className="pa-title" aria-hidden>{title}</span>
    </div>
  );
}
