"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { Shell } from "@/components/Shell";
import { Support } from "@/components/Support";
import { errorCopy } from "@/components/copy";
import { useTranslations } from "next-intl";

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
      <Support />
    </Shell>
  );
}
