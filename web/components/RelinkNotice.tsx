"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { useSignedIn } from "@/components/I18n";

/** Whether maimai DX NET refuses the signed-in person's saved login, so no new scores come in until they link again. */
export function useNeedsRelink(): boolean {
  const signedIn = useSignedIn();
  const [expired, setExpired] = useState(false);

  useEffect(() => {
    if (!signedIn) return;
    let alive = true;
    // the light answer, not /api/me: that builds the whole dashboard, and this runs on every page
    fetch("/api/me/session", { headers: { Accept: "application/json" } })
      .then((r) => (r.ok ? (r.json() as Promise<{ sessionExpired?: string }>) : null))
      .then((me) => {
        if (alive && me?.sessionExpired) setExpired(true);
      })
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [signedIn]);
  return expired;
}

/** The band across the top of every page saying so. No close button: it goes away by itself once the account is linked again. */
export function RelinkNotice() {
  const t = useTranslations("common");
  return (
    <div className="movebar tone-warning" role="alert">
      <span className="movebar-lamp" aria-hidden="true" />
      <span className="movebar-text">
        {t("relink")} <a href="/me/#relink">{t("relinkLink")}</a>
      </span>
    </div>
  );
}
