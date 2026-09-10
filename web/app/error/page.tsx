"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { Shell } from "@/components/Shell";
import { errorCopy } from "@/components/copy";

export default function ErrorPage() {
  return (
    <Suspense fallback={<div className="frame"><p className="hint" style={{ padding: "60px 0" }}>Loading…</p></div>}>
      <ErrorView />
    </Suspense>
  );
}

function ErrorView() {
  const params = useSearchParams();
  const copy = errorCopy(params.get("kind"));
  const detail = params.get("detail");

  return (
    <Shell tag="error" lit={2} footLeft="nothing was saved">
      <h1>
        {copy.headline[0]}
        <em>{copy.headline[1]}</em>.
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
