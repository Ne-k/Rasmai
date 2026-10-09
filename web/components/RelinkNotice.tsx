"use client";

import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { useSignedIn } from "@/components/I18n";

/** Across the top of every page while maimai DX NET refuses the saved sign-in, so no new scores come in until it is linked again. */
export function RelinkNotice() {
  const t = useTranslations("common");
  const signedIn = useSignedIn();
  const [expired, setExpired] = useState(false);

  useEffect(() => {
    if (!signedIn) return;
    let alive = true;
    fetch("/api/me", { headers: { Accept: "application/json" } })
      .then((r) => (r.ok ? (r.json() as Promise<{ sessionExpired?: string }>) : null))
      .then((me) => {
        if (alive && me?.sessionExpired) setExpired(true);
      })
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [signedIn]);

  if (!expired) return null;
  // no close button: it goes away by itself once the account is linked again
  return (
    <div className="movebar tone-warning" role="alert">
      <span className="movebar-lamp" aria-hidden="true" />
      <span className="movebar-text">
        {t.rich("relink", { b: (c) => <b>{c}</b> })} <a href="/me/#relink">{t("relinkLink")}</a>
      </span>
    </div>
  );
}
