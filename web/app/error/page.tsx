"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { Shell } from "@/components/Shell";
import { errorCopy } from "@/components/copy";
import { useM } from "@/components/I18n";

export default function ErrorPage() {
  const m = useM();
  return (
    <Suspense fallback={<div className="frame"><p className="hint" style={{ padding: "60px 0" }}>{m.flow.loading}</p></div>}>
      <ErrorView />
    </Suspense>
  );
}

function ErrorView() {
  const params = useSearchParams();
  const m = useM();
  const copy = errorCopy(params.get("kind"), m);
  const detail = params.get("detail");

  return (
    <Shell tag="error" lit={2} footLeft={m.flow.nothingSaved}>
      <h1>
        {copy.headline[0]}
        <em>{copy.headline[1]}</em>
        {m.flow.period}
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
    </Shell>
  );
}
