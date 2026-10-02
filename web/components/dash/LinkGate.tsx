"use client";

import { useTranslations } from "next-intl";
import type { Overview } from "./api";
import { DeleteAccount, LinkMaimai, SignIns, isWebId } from "./Identity";

/** A signed-in account with no maimai linked yet: the guided step that links one, by region. */
export function LinkGate({ me, setup, banner }: { me: Overview; setup: boolean; banner: React.ReactNode }) {
  const t = useTranslations("dash");
  const acct = useTranslations("account");
  const web = isWebId(me.user.id);
  return (
    <div className="gate link-gate">
      {setup && (
        <p className="step-tag">
          {/* the cabinet's buttons again: the step behind is gold, this one is lit */}
          <span className="step-dots" aria-hidden="true">
            <i className="done" />
            <i className="on" />
          </span>
          {acct("setupStep")}
        </p>
      )}
      <h1>{setup ? acct.rich("setupTitle", { em: (c) => <em>{c}</em> }) : t.rich("notLinkedTitle", { em: (c) => <em>{c}</em> })}</h1>
      {banner}
      <p className="lede">{acct(setup ? "setupLede" : "guidedLede")}</p>
      <LinkMaimai guided />
      {!web && (
        <a className="button ghost how-linking" href="/">
          {t("howLinking")}
        </a>
      )}
      <div className="acct-more">
        <SignIns me={me} />
        <DeleteAccount />
      </div>
    </div>
  );
}
