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
    "Confirmed traits beat 1 in 50 odds and hold up on both halves of your charts, and only those affect your picks. Leaning ones beat 1 in 20, so treat them as hints.";

  // the empty state is for a player with nothing to show on either side, which now includes what is
  // only worth watching: a list with rows in it is never called empty
  if (!weak.length && !strong.length) {
    return (
      <section className="ledger">
        <div className="ledger-head">
          <Label info={`How your scores on charts with the same pattern, note mix or BPM compare to your curve. ${gate}`}>how you play</Label>
          <span className="mono hint">
            {all.length} groups measured · {charts} scored charts
          </span>
        </div>
        <Empty>
          No clear traits yet. Every group is too close to your usual score or doesn&apos;t have enough charts. All your saved plays count,
          so more plays will help.
        </Empty>
        {largest.length ? (
          <>
            <div className="ledger-head">
              <Label info="The 4 groups furthest from your usual score. None are confirmed, so take them with a grain of salt.">biggest gaps, none confirmed</Label>
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
          <Label info={`How your scores on charts with the same pattern, note mix or BPM compare to your curve. ${gate} Pattern tags are from maiノーツ.`}>how you play</Label>
          <span className="mono hint">
            {confirmed.length} confirmed · {leaning.length} leaning
            {leaning.length && byChance ? <> (about {byChance} by chance)</> : null} · {watch.length} worth watching ·{" "}
            {even.length} about even · {charts} scored charts
          </span>
        </div>
        <div className="two-up radar-split">
          <div className="radar-wrap">
            <Info text="The middle ring is your average. Further out is better, further in is worse, and points with a ? aren't confirmed." />
            {onFamilies.length >= RADAR_MIN ? (
              <Radar axes={onFamilies} />
            ) : wheel.length >= RADAR_MIN ? (
              <Radar axes={wheel} />
            ) : (
              <p className="hint">The wheel shows up once 3 or more traits have enough charts.</p>
            )}
          </div>
          <div>
            <div className="ledger-head">
              <Label info="Traits where you score below your curve. The big number is the achievement gap and the small one is the chart count.">where you lose points</Label>
            </div>
            <List items={weak} tone="down" empty="Nothing below your average yet." />
            <div className="ledger-head">
              <Label info="Traits where you score above your curve.">where you&apos;re strong</Label>
            </div>
            <List items={strong} tone="up" empty="Nothing above your average yet." />
          </div>
        </div>
        {families?.length ? (
          <>
            <div className="ledger-head">
              <Label info="Your traits grouped by type, weighted by how many charts each one has. Click a group to see its traits.">trait groups</Label>
            </div>
            <Families families={families} />
          </>
        ) : null}
        {practice?.length ? (
          <>
            <div className="ledger-head">
              <Label info="A few charts at your level for each pattern you're weak on. Ones you've played come first so you can see if you improve.">what to work on</Label>
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
