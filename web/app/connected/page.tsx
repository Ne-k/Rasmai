"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { Shell } from "@/components/Shell";

export default function ConnectedPage() {
  return (
    <Suspense fallback={<div className="frame"><p className="hint" style={{ padding: "60px 0" }}>Loading…</p></div>}>
      <Connected />
    </Suspense>
  );
}

function Connected() {
  const params = useSearchParams();
  const player = params.get("player") ?? "";
  const region = (params.get("region") ?? "-").toUpperCase();
  const rating = params.get("rating") ?? "-";

  return (
    <Shell tag="done" lit={3} done footLeft="not affiliated with SEGA">
      <h1>
        Linked. <em>Go play.</em>
      </h1>
      <p className="lede">
        {player ? (
          <>
            Signed in as <b>{player}</b>. The bot can read your scores now.
          </>
        ) : (
          "Your maimai account is tied to your Discord account now."
        )}
      </p>

      <div className="card-row">
        <div className="stat">
          <div className="k">rating</div>
          <div className="v">{rating}</div>
        </div>
        <div className="stat">
          <div className="k">region</div>
          <div className="v">{region}</div>
        </div>
      </div>

      <h2 className="subhead">Back in Discord</h2>
      <ul className="cmds">
        <li>
          <code>/analyze</code>
          <span>the poster: what to grind, most rating first</span>
        </li>
        <li>
          <code>/plan</code>
          <span>your route to the next thousand</span>
        </li>
        <li>
          <code>/new</code>
          <span>charts you haven&apos;t played that fit your level</span>
        </li>
        <li>
          <code>/profile</code>
          <span>how you play, in numbers</span>
        </li>
      </ul>
      <p className="hint" style={{ marginTop: 18 }}>
        You can close this tab.
      </p>
    </Shell>
  );
}
