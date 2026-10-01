"use client";

import { useMemo } from "react";
import { useLocale, useM } from "@/components/I18n";
import { traitName } from "@/lib/i18n/traits";
import type { Trait, TraitFamily, TraitPractice } from "../api";
import { Empty, Info, Label, type OpenChart } from "../bits";
import { CONFIRM_CHARTS, LEAN_P, NOT_A_SKILL, RADAR_MIN, isEven, isLean, isWatch, radarAxes, twoSides, chance } from "./rules";
import { Radar } from "./Radar";
import { EvenLine, Families, List, Practice } from "./panels";
import { JudgementProfile } from "./JudgementProfile";

export { Radar, radarAxes, twoSides, JudgementProfile };

export function Traits({ traits, axes, charts, families, practice, onOpen }: { traits: Trait[]; axes: Trait[]; charts: number; families?: TraitFamily[]; practice?: TraitPractice[]; onOpen?: OpenChart }) {
  const t = useM().traitsTab;
  const locale = useLocale();
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
  const confirmed = traits.filter((x) => x.verified !== false);
  const leaning = all.filter(isLean);
  const watch = all.filter(isWatch);
  const even = all.filter(isEven).sort((a, b) => b.count - a.count);
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
  const largest = [...all].filter((x) => x.count >= CONFIRM_CHARTS)
    .sort((a, b) => Math.abs(b.offset) - Math.abs(a.offset)).slice(0, 4);
  const gate = t.gate;

  // the empty state is for a player with nothing to show on either side, which now includes what is
  // only worth watching: a list with rows in it is never called empty
  if (!weak.length && !strong.length) {
    return (
      <section className="ledger">
        <div className="ledger-head">
          <Label info={t.info(gate)}>{t.how}</Label>
          <span className="mono hint">{t.measured(all.length, charts)}</span>
        </div>
        <Empty>{t.noClear}</Empty>
        {largest.length ? (
          <>
            <div className="ledger-head">
              <Label info={t.gapsInfo}>{t.gaps}</Label>
            </div>
            <ul className="traits">
              {largest.map((x) => (
                <li key={`${x.dimension}:${x.label}`}>
                  <span className={`mono trait-offset ${x.offset < 0 ? "down" : "up"}`}>
                    {x.offset > 0 ? "+" : ""}
                    {x.offset.toFixed(2)}
                  </span>
                  <span className="trait-label">{traitName(x.label, x.english, locale)}</span>
                  <span className="mono dim">{x.count}</span>
                  <span className="trait-when">{chance(x.p)}</span>
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
          <Label info={t.info(gate) + t.tagsFrom}>{t.how}</Label>
          <span className="mono hint">
            {t.counts(confirmed.length, leaning.length)}
            {leaning.length && byChance ? t.byChance(byChance) : null}
            {t.rest(watch.length, even.length, charts)}
          </span>
        </div>
        <div className="two-up radar-split">
          <div className="radar-wrap">
            <Info text={t.wheelInfo} />
            {onFamilies.length >= RADAR_MIN ? (
              <Radar axes={onFamilies} />
            ) : wheel.length >= RADAR_MIN ? (
              <Radar axes={wheel} />
            ) : (
              <p className="hint">{t.wheelLater}</p>
            )}
          </div>
          <div>
            <div className="ledger-head">
              <Label info={t.weakInfo}>{t.weak}</Label>
            </div>
            <List items={weak} tone="down" empty={t.noWeak} />
            <div className="ledger-head">
              <Label info={t.strongInfo}>{t.strong}</Label>
            </div>
            <List items={strong} tone="up" empty={t.noStrong} />
          </div>
        </div>
        {families?.length ? (
          <>
            <div className="ledger-head">
              <Label info={t.groupsInfo}>{t.groups}</Label>
            </div>
            <Families families={families} />
          </>
        ) : null}
        {practice?.length ? (
          <>
            <div className="ledger-head">
              <Label info={t.practiceInfo}>{t.practice}</Label>
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
