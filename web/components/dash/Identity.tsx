"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { useLocale } from "@/components/I18n";
import { ProviderIcon } from "@/components/ProviderIcon";
import { isWebId } from "@/lib/ids";
import { postJSON, type Overview } from "./api";
import { Label } from "./bits";
import "./identity.css";

/** Asks the bot for the link that connects a maimai account, from the site rather than from a Discord command.
 * Each region is a button that starts linking at once; `guided` adds a line under each on how that region links. */
export function LinkMaimai({ guided = false }: { guided?: boolean }) {
  const t = useTranslations("account");
  const locale = useLocale();
  // the region being opened, so only that button says so
  const [busy, setBusy] = useState("");
  const [note, setNote] = useState("");
  const go = (chosen: string) => {
    setBusy(chosen);
    setNote("");
    postJSON<{ connectUrl?: string }>("/api/me/link-start", { region: chosen })
      .then((r) => {
        if (!r.connectUrl) throw new Error(t("linkFailed"));
        window.location.assign(r.connectUrl);
      })
      .catch((e: Error) => {
        setNote(e.message || t("linkFailed"));
        setBusy("");
      });
  };
  return (
    <div className="link-maimai">
      <div className={guided ? "region-pick" : "region-pick compact"} role="group" aria-label={guided ? t("region") : t("linkMaimai")}>
        {(["intl", "jp"] as const).map((r) => (
          // Japanese readers most likely play on the Japan version, so it is the highlighted one; nothing starts until they press it
          <button
            key={r}
            type="button"
            className={`region${r === "jp" && locale === "ja" ? " lit" : ""}${busy === r ? " busy" : ""}`}
            onClick={() => go(r)}
            disabled={Boolean(busy)}
          >
            <span className="region-dot" aria-hidden="true" />
            <span className="region-name">{!guided && busy === r ? t("linkOpening") : r === "intl" ? t("regionIntl") : t("regionJp")}</span>
            {guided && <span className="region-how">{busy === r ? t("linkOpening") : r === "intl" ? t("regionIntlHow") : t("regionJpHow")}</span>}
          </button>
        ))}
      </div>
      {note && <p className="hint bad">{note}</p>}
    </div>
  );
}

/** Which sign-ins reach this account, with a button to add the other. Linking goes through the same sign-in as the gate. */
export function SignIns({ me }: { me: Overview }) {
  const t = useTranslations("account");
  const ready = { discord: me.oauth, google: Boolean(me.google) };
  const has = (provider: "discord" | "google") => me.providers.includes(provider);
  const names = { discord: t("providerDiscord"), google: t("providerGoogle") };
  return (
    <section className="ledger">
      <div className="ledger-head">
        <Label info={t("signInsInfo")}>{t("signIns")}</Label>
      </div>
      <ul className="signin-rows">
        {(["discord", "google"] as const).map((provider) => (
          <li key={provider} className="signin-row">
            <span className={`signin-mark ${provider}`}>
              <ProviderIcon provider={provider} size={provider === "google" ? 16 : 17} />
            </span>
            <span className="signin-name">{names[provider]}</span>
            {has(provider) ? (
              <span className="ok-badge">{t("linked")}</span>
            ) : ready[provider] ? (
              <form method="post" action={`/auth/${provider}?link=1`}>
                <button type="submit" className="button ghost" aria-label={provider === "discord" ? t("linkDiscord") : t("linkGoogle")}>
                  {t("linkShort")}
                </button>
              </form>
            ) : (
              <span className="signin-off">{t("notLinked")}</span>
            )}
          </li>
        ))}
      </ul>
      {isWebId(me.user.id) && <p className="signin-note">{t("webOnlyHint")}</p>}
    </section>
  );
}

/** Deletes everything stored under this account, for someone with no maimai account linked and so no unlink button. */
export function DeleteAccount() {
  const t = useTranslations("account");
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const remove = () => {
    setBusy(true);
    postJSON("/api/me/unlink")
      .then(() => postJSON("/auth/logout"))
      .finally(() => window.location.assign("/"));
  };
  return (
    <section className="acct-delete" aria-label={t("deleteTitle")}>
      {confirm ? (
        <div className="delete-confirm">
          <p className="hint">{t("deleteHint")}</p>
          <div className="btn-row">
            <button type="button" className="button danger" onClick={remove} disabled={busy}>
              {t("deleteYes")}
            </button>
            <button type="button" className="linkish" onClick={() => setConfirm(false)}>
              {t("keepIt")}
            </button>
          </div>
        </div>
      ) : (
        <button type="button" className="linkish" onClick={() => setConfirm(true)}>
          {t("deleteAsk")}
        </button>
      )}
    </section>
  );
}
