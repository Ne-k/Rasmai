"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Turnstile } from "@/components/Turnstile";
import { InstallHint } from "@/components/Pwa";
import { Support } from "@/components/Support";
import { ProviderIcon } from "@/components/ProviderIcon";
import { Ring } from "@/components/Ring";
import { RatingPlate } from "./RatingPlate";
import "./signin-gate.css";

type Props = { oauth: boolean; google: boolean; turnstile: string; error: string; onError: (message: string) => void };

/** The dashboard for someone who is not signed in: the way in with Discord or Google, which also makes a new account. */
export function SignInGate({ oauth, google, turnstile, error, onError }: Props) {
  const t = useTranslations("dash");
  const auth = useTranslations("auth");
  const [human, setHuman] = useState("");
  const providers = [...(oauth ? ["discord" as const] : []), ...(google ? ["google" as const] : [])];
  const label = (p: "discord" | "google") => (p === "discord" ? t("signInDiscord") : auth("signInGoogle"));
  const inner = (p: "discord" | "google") => (
    <>
      <ProviderIcon provider={p} size={20} />
      <span>{label(p)}</span>
    </>
  );
  return (
    <div className="gate signin-gate">
      <div className="sg-main">
        <p className="sg-eyebrow">{t("gateEyebrow")}</p>
        <h1>{t.rich("gateTitle", { em: (c) => <em>{c}</em> })}</h1>
        <p className="lede">{t("gateLede")}</p>
        {providers.length > 0 && (
          <p className="sg-new">
            <b>{t("gateNew")}</b> {t("gateBot")}
          </p>
        )}
        {providers.length > 0 && turnstile ? (
          <form method="post" action={oauth ? "/auth/discord" : "/auth/google"} className="sg-way">
            <Turnstile siteKey={turnstile} action="dashboard" onToken={setHuman} onError={() => onError(t("turnstileFailed"))} />
            <input type="hidden" name="cf-turnstile-response" value={human} />
            {providers.map((p) => (
              <button key={p} className={`button provider ${p}`} type="submit" formAction={`/auth/${p}`} disabled={!human}>
                {inner(p)}
              </button>
            ))}
          </form>
        ) : providers.length > 0 ? (
          <div className="sg-way">
            {providers.map((p) => (
              <a key={p} className={`button provider ${p}`} href={`/auth/${p}`}>
                {inner(p)}
              </a>
            ))}
          </div>
        ) : (
          <p className="notice">{t("notSetUp")}</p>
        )}
        {error && (
          <div className="notice sg-error" role="alert">
            <span>
              {error} <Support inline />
            </span>
          </div>
        )}
        <p className="sg-privacy">
          <span className="sg-privacy-label">{t("gatePrivacyLabel")}</span>
          {t("gatePrivacy")}
        </p>
        <InstallHint />
      </div>
      {/* a sample of the screen the buttons lead to, drawn with the dashboard's own readout and plate */}
      <div className="sg-preview" aria-hidden="true">
        <Ring lit={3} size={112} />
        <div className="sg-panel">
          <div className="sg-panel-head">{t("gatePreview")}</div>
          <div className="sg-row">
            <span className="lbl">{t("rating")}</span>
            <RatingPlate rating={15234} />
          </div>
          <div className="sg-row">
            <span className="lbl">{t("newOld")}</span>
            <span className="val">4,812 · 10,422</span>
          </div>
          <div className="sg-row">
            <span className="lbl">{t("gatePreviewNext")}</span>
            <span className="val">
              Dragoon <b>+22</b>
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
