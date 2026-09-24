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
        ? `Your off-timing hits land late ${Math.round(share * 100)}% of the time: a touch behind the beat.`
        : share <= 0.4
          ? `Your off-timing hits land early ${Math.round((1 - share) * 100)}% of the time: a touch ahead of the beat.`
          : "Your off-timing hits split evenly between fast and late.";
  return (
    <section className="ledger">
      <div className="ledger-head">
        <Label info="Measured from the judgement pages of your recent plays rather than guessed from scores: how many notes of each type you hit, what each type cost, and whether you land early or late.">
          judgements
        </Label>
        <span className="mono hint">{data ? `${data.plays} plays read · ${data.lostPerPlay.toFixed(2)} points lost per play` : ""}</span>
      </div>
      {!data ? (
        <Empty>
          Needs the judgement pages of three plays. Open a play&apos;s judgements on the Recent tab, or let a read collect them: every command and the daily
          read pick up the pages for new plays.
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
                ? `${weak.kind[0].toUpperCase()}${weak.kind.slice(1)} notes cost ${Math.round(weak.lossShare * 100)}% of your loss while being worth ${Math.round((weak.stakeShare ?? weak.share) * 100)}%: the type costing you most.`
                : "No type costs more than it is worth. A break is worth five taps, so it is judged against that."}
            </p>
            {Boolean(data.bonusPerPlay) && (
              <p className="hint">
                The break bonus costs {(data.bonusPerPlay ?? 0).toFixed(2)} a play, {Math.round((data.bonusShare ?? 0) * 100)}% of your loss. Only a critical
                earns it, so that is the price of not chasing them rather than breaks going wrong. It is kept out of the types above.
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
