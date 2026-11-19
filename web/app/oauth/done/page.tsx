"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { Shell } from "@/components/Shell";
import { useTranslations } from "next-intl";

export default function DonePage() {
  const t = useTranslations("flow");
  return (
    <Suspense fallback={<div className="frame"><p className="hint" style={{ padding: "60px 0" }}>{t("loading")}</p></div>}>
      <Done />
    </Suspense>
  );
}

// The redirect of an app with no site of its own, a Discord bot say. Nothing is carried here: the app asks Rasmai for the
// player's answer itself, so the page only says which answer it was.
function Done() {
  const t = useTranslations("oauth");
  const flow = useTranslations("flow");
  const declined = useSearchParams().has("error");

  return (
    <Shell tag="authorize" lit={3} done={!declined} steps={[t("steps.check"), t("steps.approve"), t("steps.return")]} footLeft={flow("neverSeesPassword")}>
      <h1>{t(declined ? "declinedTitle" : "doneTitle")}</h1>
      <p className="lede">{t(declined ? "declinedLede" : "doneLede")}</p>
    </Shell>
  );
}
