"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { Shell } from "@/components/Shell";
import { useM } from "@/components/I18n";

export default function ConnectedPage() {
  const m = useM();
  return (
    <Suspense fallback={<div className="frame"><p className="hint" style={{ padding: "60px 0" }}>{m.flow.loading}</p></div>}>
      <Connected />
    </Suspense>
  );
}

function Connected() {
  const params = useSearchParams();
  const m = useM();
  const t = m.flow;
  const player = params.get("player") ?? "";
  const region = (params.get("region") ?? "-").toUpperCase();
  const rating = params.get("rating") ?? "-";

  return (
    <Shell tag="done" lit={3} done footLeft={m.footer.notAffiliated}>
      <h1>{t.linkedTitle}</h1>
      <p className="lede">{player ? t.signedInAs(player) : t.linkedGeneric}</p>

      <div className="card-row">
        <div className="stat">
          <div className="k">{t.rating}</div>
          <div className="v">{rating}</div>
        </div>
        <div className="stat">
          <div className="k">{t.labelRegion}</div>
          <div className="v">{region}</div>
        </div>
      </div>

      <h2 className="subhead">{t.backInDiscord}</h2>
      <ul className="cmds">
        {t.nextCommands.map(([cmd, what]) => (
          <li key={cmd}>
            <code>{cmd}</code>
            <span>{what}</span>
          </li>
        ))}
      </ul>
      <p className="hint" style={{ marginTop: 18 }}>
        {t.closeTab}
      </p>
    </Shell>
  );
}
