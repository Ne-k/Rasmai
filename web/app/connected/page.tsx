"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { Shell } from "@/components/Shell";
import { useTranslations } from "next-intl";

export default function ConnectedPage() {
  const t = useTranslations("flow");
  return (
    <Suspense fallback={<div className="frame"><p className="hint" style={{ padding: "60px 0" }}>{t("loading")}</p></div>}>
      <Connected />
    </Suspense>
  );
}

function Connected() {
  const params = useSearchParams();
  const t = useTranslations("flow");
  const footer = useTranslations("footer");
  const commandNames = { analyze: "/analyze", plan: "/plan", new: "/new", profile: "/profile" } as const;
  const player = params.get("player") ?? "";
  const region = (params.get("region") ?? "-").toUpperCase();
  const rating = params.get("rating") ?? "-";

  return (
    <Shell tag="done" lit={3} done footLeft={footer("notAffiliated")}>
      <h1>{t.rich("linkedTitle", { em: (c) => <em>{c}</em> })}</h1>
      <p className="lede">{player ? t.rich("signedInAs", { name: player, b: (c) => <b>{c}</b> }) : t("linkedGeneric")}</p>

      <div className="card-row">
        <div className="stat">
          <div className="k">{t("rating")}</div>
          <div className="v">{rating}</div>
        </div>
        <div className="stat">
          <div className="k">{t("labelRegion")}</div>
          <div className="v">{region}</div>
        </div>
      </div>

      <div className="btn-row">
        <a className="button pink" href="/me/">
          {t("openDashboard")}
        </a>
      </div>

      <h2 className="subhead">{t("usingBot")}</h2>
      <ul className="cmds">
        {Object.entries(commandNames).map(([key, cmd]) => (
          <li key={cmd}>
            <code>{cmd}</code>
            <span>{t(`nextCommands.${key as keyof typeof commandNames}`)}</span>
          </li>
        ))}
      </ul>
      <p className="hint" style={{ marginTop: 18 }}>
        {t("closeTab")}
      </p>
    </Shell>
  );
}
