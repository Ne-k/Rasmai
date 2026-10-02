"use client";

import { Fragment, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { useLocale } from "@/components/I18n";
import { getJSON, postJSON, type Overview } from "./api";
import { Label } from "./bits";

/** An account made on the site without Discord. The bot's slash commands can't reach it until Discord is linked. */
export const isWebId = (id: string) => /^w[0-9a-f]{20}$/.test(id);

/** Asks the bot for the link that connects a maimai account, from the site rather than from a Discord command.
 * `guided` swaps the dropdown for two large region buttons that start linking at once. */
export function LinkMaimai({ guided = false }: { guided?: boolean }) {
  const t = useTranslations("account");
  const locale = useLocale();
  const [region, setRegion] = useState("intl");
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
  if (guided) {
    return (
      <div className="link-maimai">
        <div className="regions">
          {(["intl", "jp"] as const).map((r) => (
            // Japanese readers most likely play on the Japan version, so it is the highlighted one; nothing starts until they press it
            <button key={r} type="button" className={r === "jp" && locale === "ja" ? "button pink" : "button"} onClick={() => go(r)} disabled={Boolean(busy)}>
              {busy === r ? t("linkOpening") : r === "intl" ? t("regionIntl") : t("regionJp")}
            </button>
          ))}
        </div>
        <p className="hint">{t("regionNote")}</p>
        {note && <p className="hint bad">{note}</p>}
      </div>
    );
  }
  return (
    <div className="link-maimai">
      <div className="btn-row">
        <select value={region} onChange={(e) => setRegion(e.target.value)} aria-label={t("region")} disabled={Boolean(busy)}>
          <option value="intl">{t("regionIntl")}</option>
          <option value="jp">{t("regionJp")}</option>
        </select>
        <button type="button" className="button pink" onClick={() => go(region)} disabled={Boolean(busy)}>
          {busy ? t("linkOpening") : t("linkMaimai")}
        </button>
      </div>
      {note && <p className="hint bad">{note}</p>}
    </div>
  );
}

type Identities = { providers: string[]; linked: boolean; webOnly: boolean };

/** Which sign-ins reach this account, with a button to add the other. Linking goes through the same sign-in as the gate. */
export function SignIns({ me }: { me: Overview }) {
  const t = useTranslations("account");
  const [found, setFound] = useState<Identities | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    getJSON<Identities>("/api/me/identities")
      .then(setFound)
      .catch(() => setFailed(true));
  }, []);
  const ready = { discord: me.oauth, google: Boolean(me.google) };
  const has = (provider: "discord" | "google") => Boolean(found?.providers.includes(provider));
  const names = { discord: t("providerDiscord"), google: t("providerGoogle") };
  return (
    <section className="ledger">
      <div className="ledger-head">
        <Label info={t("signInsInfo")}>{t("signIns")}</Label>
      </div>
      {failed ? (
        <p className="hint">{t("signInsFailed")}</p>
      ) : found ? (
        <>
          <dl className="facts">
            {(["discord", "google"] as const).map((provider) => (
              <Fragment key={provider}>
                <dt>{names[provider]}</dt>
                <dd>{has(provider) ? t("linked") : t("notLinked")}</dd>
              </Fragment>
            ))}
          </dl>
          <div className="btn-row">
            {(["discord", "google"] as const).map(
              (provider) =>
                !has(provider) &&
                ready[provider] && (
                  <form key={provider} method="post" action={`/auth/${provider}?link=1`}>
                    <button type="submit" className="button ghost">
                      {provider === "discord" ? t("linkDiscord") : t("linkGoogle")}
                    </button>
                  </form>
                ),
            )}
          </div>
          {found.webOnly && <p className="hint">{t("webOnlyHint")}</p>}
        </>
      ) : (
        <p className="hint">{t("loading")}</p>
      )}
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
    <section className="ledger">
      <div className="ledger-head">
        <Label>{t("deleteTitle")}</Label>
      </div>
      <p className="hint">{t("deleteHint")}</p>
      {confirm ? (
        <div className="btn-row">
          <button type="button" className="button pink" onClick={remove} disabled={busy}>
            {t("deleteYes")}
          </button>
          <button type="button" className="button ghost" onClick={() => setConfirm(false)}>
            {t("keepIt")}
          </button>
        </div>
      ) : (
        <button type="button" className="button ghost" onClick={() => setConfirm(true)}>
          {t("deleteAsk")}
        </button>
      )}
    </section>
  );
}
