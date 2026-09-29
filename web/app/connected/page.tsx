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
        You&apos;re <em>linked</em>.
      </h1>
      <p className="lede">
        {player ? (
          <>
            Signed in as <b>{player}</b>. Rasmai can check your scores now.
          </>
        ) : (
          "Your maimai account is now linked to your Discord account."
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
          <span>what to grind, biggest gains first</span>
        </li>
        <li>
          <code>/plan</code>
          <span>a plan for your next thousand</span>
        </li>
        <li>
          <code>/new</code>
          <span>charts you haven&apos;t played that fit your level</span>
        </li>
        <li>
          <code>/profile</code>
          <span>how you play and where you lose points</span>
        </li>
      </ul>
      <p className="hint" style={{ marginTop: 18 }}>
        You can close this tab.
      </p>
    </Shell>
  );
}
