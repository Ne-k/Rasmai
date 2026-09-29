"use client";

import type { JudgementProfileData } from "../api";
import { Empty, Info, Label } from "../bits";

export function JudgementProfile({ data }: { data: JudgementProfileData | null }) {
  const weak = data?.types.find((t) => t.kind === data.weak);
  const share = data?.lateShare ?? null;
  const timing =
    share === null
      ? ""
      : share >= 0.6
        ? `${Math.round(share * 100)}% of your off-timing hits are late, so you're a bit behind the beat.`
        : share <= 0.4
          ? `${Math.round((1 - share) * 100)}% of your off-timing hits are early, so you're a bit ahead of the beat.`
          : "Your off-timing hits are about half fast, half late.";
  return (
    <section className="ledger">
      <div className="ledger-head">
        <Label info="From the judgement pages of your recent plays. Shows what each note type costs you and whether you hit early or late.">
          judgements
        </Label>
        <span className="mono hint">{data ? `${data.plays} plays · ${data.lostPerPlay.toFixed(2)} points lost per play` : ""}</span>
      </div>
      {!data ? (
        <Empty>
          Needs judgement data from 3 plays. Open a play&apos;s judgements on the Recent tab, hit refresh on the Account tab, or run any
          command in Discord.
        </Empty>
      ) : (
        <div className="two-up">
          {/* six columns will not fit a phone, and this table keeps its shape rather than becoming
              cards, so it scrolls sideways inside its own box instead of pushing the page out */}
          <div className="scroll">
          <table className="tbl compact keep judge-profile">
            <thead>
              <tr>
                <th>notes</th>
                <th className="c-num">of the notes</th>
                <th className="c-num">worth</th>
                <th className="c-num">of the loss</th>
                <th className="c-num">lost per 100</th>
                <th className="c-num">clean</th>
              </tr>
            </thead>
            <tbody>
              {data.types.map((t) => (
                <tr key={t.kind} data-kind={t.kind} className={t.kind === data.weak ? "weak" : ""}>
                  <td className="mono kind">{t.kind}</td>
                  <td className="c-num mono">{Math.round(t.share * 100)}%</td>
                  <td className="c-num mono dim">{Math.round((t.stakeShare ?? t.share) * 100)}%</td>
                  <td className="c-num mono">{Math.round(t.lossShare * 100)}%</td>
                  <td className="c-num mono">{t.per100.toFixed(2)}</td>
                  <td className="c-num mono dim">{Math.round(t.clean * 100)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
          <div>
            <p className="hint">
              {weak
                ? `${weak.kind[0].toUpperCase()}${weak.kind.slice(1)} notes are ${Math.round(weak.lossShare * 100)}% of your lost points but only worth ${Math.round((weak.stakeShare ?? weak.share) * 100)}%, so they cost you the most.`
                : "No note type costs you more than it's worth. A break counts as five taps here."}
            </p>
            {Boolean(data.bonusPerPlay) && (
              <p className="hint">
                Missed break bonus costs you {(data.bonusPerPlay ?? 0).toFixed(2)} per play, {Math.round((data.bonusShare ?? 0) * 100)}% of your loss. Only
                critical breaks get it, so this comes from missing criticals. It isn&apos;t counted in the table.
              </p>
            )}
            <ul className="bars">
              <li>
                <span>fast</span>
                <span className="bar">
                  <span style={{ width: `${data.fast + data.late ? (100 * data.fast) / (data.fast + data.late) : 0}%` }} />
                </span>
                <span className="v">{data.fast}</span>
              </li>
              <li>
                <span>late</span>
                <span className="bar">
                  <span style={{ width: `${data.fast + data.late ? (100 * data.late) / (data.fast + data.late) : 0}%` }} />
                </span>
                <span className="v">{data.late}</span>
              </li>
            </ul>
            {timing ? <p className="hint">{timing}</p> : null}
          </div>
        </div>
      )}
    </section>
  );
}
