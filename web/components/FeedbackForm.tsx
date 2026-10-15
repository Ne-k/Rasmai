"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Turnstile } from "@/components/Turnstile";

const MAX = 1000;
const MAX_CONTACT = 200;
const ASKS = ["liked", "annoyed", "wish"] as const;

type Answers = { liked: string; annoyed: string; wish: string; contact: string };
const EMPTY: Answers = { liked: "", annoyed: "", wish: "", contact: "" };

/** The feedback form: a rating that has to be given, three open questions and a contact that are both optional, and the human check when the site has one. */
export function FeedbackForm({ siteKey }: { siteKey: string }) {
  const t = useTranslations("feedback");
  const [rating, setRating] = useState(0);
  const [answers, setAnswers] = useState<Answers>(EMPTY);
  const [token, setToken] = useState("");
  const [state, setState] = useState<"idle" | "sending" | "sent">("idle");
  const [error, setError] = useState("");
  // a token verifies once, so a second answer needs a fresh widget
  const [round, setRound] = useState(0);

  const known = (code: string) => (t.has(`errors.${code}` as never) ? code : "generic");

  const send = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!rating) {
      setError("needRating");
      return;
    }
    setState("sending");
    setError("");
    try {
      const response = await fetch("/api/feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ rating, ...answers, token }),
      });
      const body = (await response.json().catch(() => ({}))) as { ok?: boolean; error?: string };
      if (response.ok && body.ok) {
        setState("sent");
        return;
      }
      setError(known(String(body.error ?? "generic")));
    } catch {
      setError("generic");
    }
    setState("idle");
    setToken("");
    setRound((n) => n + 1);
  };

  if (state === "sent") {
    return (
      <div className="fb fb-thanks" role="status">
        <h2>{t("thanksTitle")}</h2>
        <p>{t("thanks")}</p>
        <button
          type="button"
          className="button"
          onClick={() => {
            setRating(0);
            setAnswers(EMPTY);
            setToken("");
            setRound((n) => n + 1);
            setState("idle");
          }}
        >
          {t("another")}
        </button>
      </div>
    );
  }

  return (
    <form className="fb" onSubmit={send} noValidate>
      <fieldset>
        <legend className="fb-q">{t("rateLabel")}</legend>
        <div className="fb-rates" role="radiogroup" aria-label={t("rateLabel")}>
          {[1, 2, 3, 4, 5].map((n) => (
            <label key={n} className="fb-rate">
              <input type="radio" name="rating" value={n} checked={rating === n} onChange={() => {
                  setRating(n);
                  setError("");        // the message that asked for a rating has been answered
                }}
              />
              <span>
                <b>{n}</b>
                {t(`rates.${n}` as never)}
              </span>
            </label>
          ))}
        </div>
      </fieldset>

      {ASKS.map((key) => (
        <div key={key}>
          <label className="fb-q" htmlFor={`fb-${key}`}>
            {t(`${key}Label` as never)}
          </label>
          <p className="fb-hint">{t(`${key}Hint` as never)}</p>
          <textarea
            id={`fb-${key}`}
            value={answers[key]}
            maxLength={MAX}
            onChange={(e) => setAnswers({ ...answers, [key]: e.target.value })}
          />
          <p className="fb-count" aria-hidden="true">
            {answers[key].length} / {MAX}
          </p>
        </div>
      ))}

      <div>
        <label className="fb-q" htmlFor="fb-contact">
          {t("contactLabel")}
        </label>
        <p className="fb-hint">{t("contactHint")}</p>
        <input id="fb-contact" type="text" value={answers.contact} maxLength={MAX_CONTACT} autoComplete="off" onChange={(e) => setAnswers({ ...answers, contact: e.target.value })} />
      </div>

      {siteKey ? (
        <div>
          <p className="fb-hint">{t("checkHint")}</p>
          <Turnstile
            key={round}
            siteKey={siteKey}
            action="feedback"
            onToken={(value) => {
              setToken(value);
              if (value) setError((e) => (e === "check_failed" ? "" : e));
            }}
            onError={() => {
              setToken("");
              setError("check_failed");
            }}
          />
        </div>
      ) : null}
      {error ? (
        <p className="fb-error" role="alert">
          {t(`errors.${error}` as never)}
        </p>
      ) : null}
      <div className="btn-row">
        <button type="submit" className="button pink" disabled={state === "sending" || (Boolean(siteKey) && !token)}>
          {state === "sending" ? t("sending") : t("send")}
        </button>
        <span className="fb-hint">{t("anon")}</span>
      </div>
    </form>
  );
}
