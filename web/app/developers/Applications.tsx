"use client";

import { useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { Gate, Icon, Lamp, home, useApps } from "./shared";

export function Applications() {
  const t = useTranslations("developers");
  const state = useApps();
  const { apps, max, reviews, busy, problem, setProblem, call } = state;
  const dialog = useRef<HTMLDialogElement>(null);
  const [name, setName] = useState("");
  const full = (apps?.length ?? 0) >= max;

  const create = async (event: React.FormEvent) => {
    event.preventDefault();
    if (busy) return;
    const made = await call("", { name: name.trim() });
    if (made?.app) window.location.assign(`${home()}/applications/${made.app.id}/`);
  };

  return (
    <Gate state={state}>
      <div className="dp-head">
        <h1>{t("applications")}</h1>
        <button
          type="button"
          className="button pink"
          disabled={full}
          onClick={() => {
            setName("");
            setProblem("");
            dialog.current?.showModal();
          }}
        >
          {t("new")}
        </button>
      </div>
      <p className="dp-note">{t("lede")}</p>
      {apps?.length ? (
        <ul className="dp-apps" data-reviews={reviews || undefined}>
          {apps.map((app) => (
            <li key={app.id}>
              <a href={`${home()}/applications/${app.id}/`}>
                {reviews && <Lamp review={app.review} />}
                <Icon app={app} />
                <b>
                  {app.name}
                  {app.blocked && <small> · {t("blockedTag")}</small>}
                </b>
                <span className="dp-id">{app.id}</span>
                {reviews && <span>{t(`review.${app.review}`)}</span>}
              </a>
            </li>
          ))}
        </ul>
      ) : (
        <p className="hint">{t("none")}</p>
      )}
      {full && <p className="hint">{t("full", { max })}</p>}

      <dialog ref={dialog} aria-labelledby="dp-new">
        <form onSubmit={create}>
          <h2 id="dp-new">{t("new")}</h2>
          <label>
            {t("name")}
            <input type="text" value={name} onChange={(e) => setName(e.target.value)} maxLength={40} required autoComplete="off" />
          </label>
          <p className="hint">{t("nameHint")}</p>
          {problem && <p className="hint bad" role="alert">{problem}</p>}
          <div className="btn-row">
            <button type="button" className="button ghost" onClick={() => dialog.current?.close()}>{t("cancel")}</button>
            <button type="submit" className="button pink" disabled={busy || !name.trim()}>{t("create")}</button>
          </div>
        </form>
      </dialog>
    </Gate>
  );
}
