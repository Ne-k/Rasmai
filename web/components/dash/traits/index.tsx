"use client";

import { useMemo, useState } from "react";
import type { Trait, TraitFamily, TraitPractice } from "../api";
import { Empty, Info, Label, type OpenChart } from "../bits";
import { CONFIRM_CHARTS, LEAN, LEAN_P, NOT_A_SKILL, RADAR_FILL, RADAR_MIN, isEven, isLean, isWatch, radarAxes, twoSides, chance, odds } from "./rules";
import { Radar } from "./Radar";
import { EvenLine, Families, List, Practice } from "./panels";
import { JudgementProfile } from "./JudgementProfile";

export { Radar, radarAxes, twoSides, JudgementProfile };

export function Traits({ traits, axes, charts, families, practice, onOpen }: { traits: Trait[]; axes: Trait[]; charts: number; families?: TraitFamily[]; practice?: TraitPractice[]; onOpen?: OpenChart }) {
  // the confirmed list arrives already filtered; the leaning and level ones are built here, so
  // the same rule has to be applied before anything is counted or drawn
  const all = useMemo(() => (axes ?? []).filter((a) => !NOT_A_SKILL.has(a.dimension)), [axes]);
  const wheel = useMemo(() => radarAxes(all), [all]);
  // a family is drawn as an axis like any other, but it is never "leaning": it is as sure as what
  // is under it, and the list below says how much that is
  const onFamilies = useMemo(
    () => (families ?? []).map((f) => ({ dimension: "family", label: f.label, english: f.label, offset: f.offset,
                                         count: f.charts, plays: f.plays, p: 0, verified: f.verified,
                                         leaning: !f.verified })),
    [families],
  );
  const confirmed = traits.filter((t) => t.verified !== false);
  const leaning = all.filter(isLean);
  const watch = all.filter(isWatch);
  const even = all.filter(isEven).sort((a, b) => b.count - a.count);
  const shown = [...confirmed, ...leaning];
  // Both lists are filled from the same order - confirmed, then leaning, then worth watching - so
  // the strongest evidence always leads and the rest is there to give the tab a shape. A confirmed
  // trait is never dropped to make the two sides match: they are levelled up, never down.
  // A lean is a trait shuffled tags matched less than one time in twenty. Over the couple of dozen
  // groups a player has enough charts for, that alone produces about one, and the reader deserves
  // to know how much of the list to discount. It is an upper estimate: a lean also has to sit a way
  // out from the player's own middle, which chance clears less often than the odds alone suggest.
  const byChance = Math.round(
    (confirmed.length + leaning.length + watch.length + even.length) * LEAN_P,
  );
  const { weak, strong } = twoSides(confirmed, all);
  const largest = [...all].filter((t) => t.count >= CONFIRM_CHARTS)
    .sort((a, b) => Math.abs(b.offset) - Math.abs(a.offset)).slice(0, 4);
  const gate =
    "Confirmed: rarer than 1 in 50 under shuffled tags, and the same sign in both halves of your charts. Leaning: rarer than 1 in 20, so read it as a hint. Worth watching: not yet separable from chance. Only confirmed traits steer your picks.";

  // the empty state is for a player with nothing to show on either side, which now includes what is
  // only worth watching: a list with rows in it is never called empty
  if (!weak.length && !strong.length) {
    return (
      <section className="ledger">
        <div className="ledger-head">
          <Label info={`Your traits: what your charts share, a pattern, a note mix, a tempo band, an era, a designer, scored by how far your results sit from your own curve. Once enough plays are stored, each note type joins them, measured from your judgement pages rather than inferred from scores. ${gate}`}>how you play</Label>
          <span className="mono hint">
            {all.length} groups measured · {charts} scored charts
          </span>
        </div>
        <Empty>
          Nothing separates from noise yet. Every trait group measured sits too close to your usual score to trust, or has too few charts behind it. Every recorded
          play counts, not only your bests, so more plays sharpen this.
        </Empty>
        {largest.length ? (
          <>
            <div className="ledger-head">
              <Label info="The four groups furthest from your usual score. None passed the gate, so treat them as things to watch, not facts.">largest measured, none confirmed</Label>
            </div>
            <ul className="traits">
              {largest.map((t) => (
                <li key={`${t.dimension}:${t.label}`}>
                  <span className={`mono trait-offset ${t.offset < 0 ? "down" : "up"}`}>
                    {t.offset > 0 ? "+" : ""}
                    {t.offset.toFixed(2)}
                  </span>
                  <span className="trait-label">{t.english ?? t.label}</span>
                  <span className="mono dim">{t.count}</span>
                  <span className="trait-when">{chance(t.p)}</span>
                </li>
              ))}
            </ul>
          </>
        ) : null}
        {even.length ? <EvenLine even={even} /> : null}
      </section>
    );
  }
  return (
    <>
      <section className="ledger">
        <div className="ledger-head">
          <Label info={`Your traits: what your charts share, a pattern, a note mix, a tempo band, an era, a designer, scored by how far your results sit from your own curve. Once enough plays are stored, each note type joins them, measured from your judgement pages rather than inferred from scores. Every tag is fitted together over your bests and every recorded play, with play count and difficulty held fixed. ${gate} Patterns and note mixes come from maiノーツ.`}>how you play</Label>
          <span className="mono hint">
            {confirmed.length} confirmed · {leaning.length} leaning
            {leaning.length && byChance ? <> (about {byChance} by chance)</> : null} · {watch.length} worth watching ·{" "}
            {even.length} level with the rest · {charts} scored charts
          </span>
        </div>
        <div className="two-up radar-split">
          <div className="radar-wrap">
            <Info text="Each axis is a play trait: patterns, note mix, tempo, density. The middle ring is your own average, so further out is above it and further in is below. Hollow grey points with a ? are not confirmed." />
            {onFamilies.length >= RADAR_MIN ? (
              <Radar axes={onFamilies} />
            ) : wheel.length >= RADAR_MIN ? (
              <Radar axes={wheel} />
            ) : (
              <p className="hint">The wheel appears once three or more play traits have enough charts behind them.</p>
            )}
          </div>
          <div>
            <div className="ledger-head">
              <Label info="Traits where your scores sit below your own curve. The number is the gap in achievement points, and the small figure counts the charts behind it.">where you lose points</Label>
            </div>
            <List items={weak} tone="down" empty="Nothing sits below your own average yet." />
            <div className="ledger-head">
              <Label info="Traits where your scores sit above your own curve.">where you shine</Label>
            </div>
            <List items={strong} tone="up" empty="Nothing sits above your own average yet." />
          </div>
        </div>
        {families?.length ? (
          <>
            <div className="ledger-head">
              <Label info="Your traits grouped by what they ask of you. A family is weighted by the charts behind it, so a tag measured on nine charts counts about a ninth of one measured on ninety. Open a family to see its traits.">what each part of your play asks</Label>
            </div>
            <Families families={families} />
          </>
        ) : null}
        {practice?.length ? (
          <>
            <div className="ledger-head">
              <Label info="For each pattern you score below your curve on, a few charts in your own working band that carry it. Ones you already hold a score on come first, so a rerun shows the change.">what to work on</Label>
            </div>
            <Practice items={practice} onOpen={onOpen} />
          </>
        ) : null}
        {even.length ? <EvenLine even={even} /> : null}
      </section>
    </>
  );
}

/** What the judgement pages of the recent plays say, measured rather than inferred: where the points go, and early or late. */
