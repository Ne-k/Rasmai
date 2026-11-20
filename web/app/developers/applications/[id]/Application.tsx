"use client";

import { useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { type App, Copy, Gate, Icon, Lamp, home, site, useApps } from "../../shared";

type Draft = Pick<App, "name" | "description" | "website" | "privacy" | "redirects">;
const draftOf = ({ name, description, website, privacy, redirects }: App): Draft => ({ name, description, website, privacy, redirects });

const ICON_BYTES = 256 * 1024;
// the developer's own machine, as the bot reads it: such a redirect needs no review
const local = (redirect: string) => {
  try {
    return ["localhost", "127.0.0.1"].includes(new URL(redirect).hostname);
  } catch {
    return false;
  }
};

function Field({ label, hint, htmlFor, children }: { label: string; hint?: string; htmlFor?: string; children: React.ReactNode }) {
  const name = (
    <>
      {label}
      {hint && <small>{hint}</small>}
    </>
  );
  return (
    <div className="dp-field">
      {htmlFor ? <label htmlFor={htmlFor}>{name}</label> : <span>{name}</span>}
      <div>{children}</div>
    </div>
  );
}

export function Application({ id }: { id: string }) {
  const t = useTranslations("developers");
  const state = useApps();
  const { apps, maxRedirects, reviews, donePage, busy, problem, setProblem, call } = state;
  const app = apps?.find((one) => one.id === id);
  const [section, setSection] = useState<"general" | "oauth2">("general");
  // the fields as edited; null while they are as saved
  const [edited, setEdited] = useState<Draft | null>(null);
  const [secret, setSecret] = useState("");
  const [asking, setAsking] = useState<"delete" | "secret">("delete");
  const confirm = useRef<HTMLDialogElement>(null);
  const picture = useRef<HTMLInputElement>(null);

  if (!app) {
    return (
      <Gate state={state}>
        {/* only once the apps are read: before that this also renders on the server, where home() has no window */}
        {apps && (
          <section className="dp-gate">
            <p className="dp-note">{t("missing")}</p>
            <a href={`${home()}/applications/`}>{t("back")}</a>
          </section>
        )}
      </Gate>
    );
  }

  const draft = edited ?? draftOf(app);

  /** Send a chosen picture as it is. The bot decides whether it is one, and keeps only its own redrawing of it. */
  const pick = (event: React.ChangeEvent<HTMLInputElement>) => {
    const chosen = event.target.files?.[0];
    event.target.value = "";
    if (!chosen) return;
    // an empty file would read as no picture at all, which is how one is removed
    if (!chosen.size || chosen.size > ICON_BYTES) return setProblem(t("problems.bad_icon"));
    const reader = new FileReader();
    reader.onload = () => call("/icon", { id, image: String(reader.result).split(",")[1] ?? "" });
    reader.readAsDataURL(chosen);
  };
  const dirty = JSON.stringify(draft) !== JSON.stringify(draftOf(app));
  const edit = (change: Partial<Draft>) => setEdited({ ...draft, ...change });
  const editRedirect = (at: number, value: string) => edit({ redirects: draft.redirects.map((old, i) => (i === at ? value : old)) });

  const save = async (event: React.FormEvent) => {
    event.preventDefault();
    if (busy || !dirty) return;
    const saved = await call("/update", {
      id,
      name: draft.name.trim(),
      description: draft.description.trim(),
      website: draft.website.trim(),
      privacy: draft.privacy.trim(),
      redirects: draft.redirects.map((redirect) => redirect.trim()).filter(Boolean),
    });
    if (saved) setEdited(null);
  };

  const ask = (what: "delete" | "secret") => {
    setAsking(what);
    setProblem("");
    confirm.current?.showModal();
  };
  const confirmed = async () => {
    if (asking === "delete") {
      if (await call("/delete", { id })) window.location.assign(`${home()}/applications/`);
      return;
    }
    const made = await call("/secret", { id });
    if (!made?.secret) return;
    setSecret(made.secret);
    confirm.current?.close();
  };

  // what a review asks for, read off the app as saved: that is what the reviewer gets
  const needs = [
    ["name", Boolean(app.name)],
    ["website", app.website.startsWith("https://")],
    ["privacy", app.privacy.startsWith("https://")],
    ["redirect", app.redirects.some((redirect) => !local(redirect))],
  ] as const;
  // an authorize link is for a redirect to the app's own site: the done page's links are started by the app itself
  const toSite = app.redirects.find((redirect) => redirect !== donePage);
  const example =
    toSite &&
    `${site()}/oauth/authorize?${new URLSearchParams({ response_type: "code", client_id: app.id, redirect_uri: toSite, scope: "maimai:clal", state: "STATE", code_challenge: "CODE_CHALLENGE", code_challenge_method: "S256" })}`;

  return (
    <div className="dp-body">
      <nav className="dp-side" aria-label={t("sections")}>
        <a href={`${home()}/applications/`}>{t("back")}</a>
        <strong>{app.name}</strong>
        {(["general", "oauth2"] as const).map((key) => (
          <button type="button" key={key} aria-current={section === key ? "page" : undefined} onClick={() => setSection(key)}>
            {t(`section.${key}`)}
          </button>
        ))}
      </nav>

      <form onSubmit={save}>
        <h1>{t(`section.${section}`)}</h1>
        {app.blocked && <p className="hint bad" role="status">{t("blocked")}</p>}
        {section === "general" ? (
          <>
            <section className="dp-sec">
              <Field label={t("icon")} hint={t("iconHint")}>
                <Icon app={app} size={64} />
                <input ref={picture} type="file" accept="image/png,image/jpeg,image/webp" hidden onChange={pick} />
                <button type="button" className="button ghost dp-mini" disabled={busy} onClick={() => picture.current?.click()}>
                  {t(app.icon ? "iconChange" : "iconUpload")}
                </button>
                {app.icon && (
                  <button type="button" className="button ghost dp-mini" disabled={busy} onClick={() => call("/icon", { id, image: "" })}>
                    {t("remove")}
                  </button>
                )}
              </Field>
              <Field label={t("name")} hint={t("nameHint")} htmlFor="dp-name">
                <input id="dp-name" type="text" value={draft.name} onChange={(e) => edit({ name: e.target.value })} maxLength={40} required autoComplete="off" />
              </Field>
              <Field label={t("description")} htmlFor="dp-description">
                <textarea id="dp-description" value={draft.description} onChange={(e) => edit({ description: e.target.value })} maxLength={200} rows={3} />
              </Field>
              <Field label={t("website")} htmlFor="dp-website">
                <input id="dp-website" type="url" value={draft.website} onChange={(e) => edit({ website: e.target.value })} maxLength={200} placeholder="https://" autoCapitalize="none" spellCheck={false} />
              </Field>
              <Field label={t("privacy")} htmlFor="dp-privacy">
                <input id="dp-privacy" type="url" value={draft.privacy} onChange={(e) => edit({ privacy: e.target.value })} maxLength={200} placeholder="https://" autoCapitalize="none" spellCheck={false} />
              </Field>
              <Field label={t("applicationId")}>
                <code>{app.id}</code>
                <Copy text={app.id} />
              </Field>
            </section>

            {reviews && (
            <section className="dp-sec">
              <h2>{t("verification")}</h2>
              <p className="dp-state">
                <Lamp review={app.review} />
                {t(`review.${app.review}`)}
              </p>
              <p className="dp-note">{t(`reviewNote.${app.review}`)}</p>
              {(app.review === "none" || app.review === "rejected") && (
                <>
                  <p className="dp-note">{t("needs")}</p>
                  <ul className="dp-needs">
                    {needs.map(([key, met]) => (
                      <li key={key}>
                        {t(`need.${key}`)}
                        <span data-met={met || undefined}>{met ? t("met") : t("unmet")}</span>
                      </li>
                    ))}
                  </ul>
                  <div className="btn-row">
                    <button type="button" className="button" disabled={busy || dirty || needs.some(([, met]) => !met)} onClick={() => call("/review", { id })}>
                      {t("requestReview")}
                    </button>
                    {dirty && <span className="hint">{t("saveFirst")}</span>}
                  </div>
                </>
              )}
            </section>
            )}

            <section className="dp-sec">
              <h2>{t("delete")}</h2>
              <p className="dp-note">{t("deleteNote")}</p>
              <div className="btn-row">
                <button type="button" className="button ghost" onClick={() => ask("delete")}>{t("delete")}</button>
              </div>
            </section>
          </>
        ) : (
          <>
            <section className="dp-sec">
              <Field label={t("clientId")}>
                <code>{app.id}</code>
                <Copy text={app.id} />
              </Field>
              <Field label={t("clientSecret")}>
                {secret ? (
                  <>
                    <code>{secret}</code>
                    <Copy text={secret} />
                    <p className="hint bad" role="status">{t("secretOnce")}</p>
                  </>
                ) : (
                  <>
                    <span>{app.hasSecret ? t("secretSet") : t("secretNone")}</span>
                    <button type="button" className="button ghost dp-mini" onClick={() => ask("secret")}>{t("resetSecret")}</button>
                  </>
                )}
              </Field>
            </section>

            <section className="dp-sec">
              <h2>{t("redirects")}</h2>
              <p className="dp-note">{t("redirectsNote")}</p>
              <ul className="dp-rows">
                {draft.redirects.map((redirect, at) => (
                  <li key={at}>
                    <input type="url" value={redirect} onChange={(e) => editRedirect(at, e.target.value)} maxLength={200} placeholder="https://" aria-label={t("redirect", { n: at + 1 })} autoCapitalize="none" spellCheck={false} />
                    <button type="button" className="button ghost dp-mini" onClick={() => edit({ redirects: draft.redirects.filter((_, i) => i !== at) })}>{t("remove")}</button>
                  </li>
                ))}
              </ul>
              <div className="btn-row">
                <button type="button" className="button ghost" disabled={draft.redirects.length >= maxRedirects} onClick={() => edit({ redirects: [...draft.redirects, ""] })}>{t("addRedirect")}</button>
                {donePage && !draft.redirects.includes(donePage) && (
                  <button type="button" className="button ghost" disabled={draft.redirects.length >= maxRedirects} onClick={() => edit({ redirects: [...draft.redirects, donePage] })}>{t("donePageAdd")}</button>
                )}
              </div>
              <p className="dp-note">{t("donePageNote")}</p>
            </section>

            <section className="dp-sec">
              <h2>{t("endpoints")}</h2>
              {(["authorize", "token", "userinfo"] as const).map((key) => (
                <Field key={key} label={t(key)}>
                  <code>{`${site()}/oauth/${key}`}</code>
                  <Copy text={`${site()}/oauth/${key}`} />
                </Field>
              ))}
              <Field label={t("scope")}>
                <code>maimai:clal</code>
              </Field>
              <Field label={t("example")} hint={example ? t("exampleNote") : undefined}>
                {example ? (
                  <>
                    <code className="dp-long">{example}</code>
                    <Copy text={example} />
                  </>
                ) : (
                  <span>{t("exampleNone")}</span>
                )}
              </Field>
            </section>
          </>
        )}

        {problem && <p className="hint bad" role="alert">{problem}</p>}
        {dirty && (
          <div className="dp-save">
            <span role="status">{t("unsaved")}</span>
            <button type="button" className="button ghost" disabled={busy} onClick={() => setEdited(null)}>{t("reset")}</button>
            <button type="submit" className="button pink" disabled={busy}>{t("save")}</button>
          </div>
        )}
      </form>

      <dialog ref={confirm} aria-labelledby="dp-confirm">
        <h2 id="dp-confirm">{asking === "delete" ? t("deleteConfirm", { name: app.name }) : t("secretConfirm")}</h2>
        <p>{asking === "delete" ? t("deleteWarning") : t("secretWarning")}</p>
        {problem && <p className="hint bad" role="alert">{problem}</p>}
        <div className="btn-row">
          <button type="button" className="button ghost" onClick={() => confirm.current?.close()}>{t("cancel")}</button>
          <button type="button" className="button" disabled={busy} onClick={confirmed}>{asking === "delete" ? t("delete") : t("resetSecret")}</button>
        </div>
      </dialog>
    </div>
  );
}
