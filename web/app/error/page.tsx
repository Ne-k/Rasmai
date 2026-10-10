"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { Shell } from "@/components/Shell";
import { Support } from "@/components/Support";
import { errorCopy } from "@/components/copy";
import { useTranslations } from "next-intl";

const LINK_STILL_WORKS = new Set(["upstream", "maintenance", "no_login", "verify", "credentials"]);

export default function ErrorPage() {
  const t = useTranslations("flow");
  return (
    <Suspense fallback={<div className="frame"><p className="hint" style={{ padding: "60px 0" }}>{t("loading")}</p></div>}>
      <ErrorView />
    </Suspense>
  );
}

function ErrorView() {
  const params = useSearchParams();
  const t = useTranslations("flow");
  const e = useTranslations("errors");
  const copy = errorCopy(params.get("kind"), e);
  const detail = params.get("detail");
  const code = params.get("code") ?? "";
  const user = params.get("user") ?? "";
  // the errors whose hint says the login link still works: on a phone, finding it again in Discord was the hard part
  const back = LINK_STILL_WORKS.has(params.get("kind") ?? "") && /^[A-Za-z0-9_-]{20,64}$/.test(code) && /^[A-Za-z0-9_.:-]{1,200}$/.test(user)
    ? `/connect/?${new URLSearchParams({ code, user })}`
    : "";

  return (
    <Shell tag="error" lit={2} footLeft={t("nothingSaved")}>
      <h1>
        {copy.headline}
        {t("period")}
      </h1>
      <p className="lede">
        {copy.detail}
        {detail && (
          <>
            <br />
            <code>{detail}</code>
          </>
        )}
      </p>
      <div className="aside">{copy.hint}</div>
      {back ? (
        <div className="btn-row">
          <a className="button pink" href={back}>
            {t("backToLink")}
          </a>
        </div>
      ) : null}
      <Support />
    </Shell>
  );
}
