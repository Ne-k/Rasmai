import { useRef, useState } from "react";
import { useDismiss } from "@/components/Term";
import { Support } from "@/components/Support";
import { useTranslations } from "next-intl";
import { activeT, activeTag } from "@/lib/i18n/active";

const TIER: Record<string, string> = {
  basic: "BASIC",
  advanced: "ADVANCED",
  expert: "EXPERT",
  master: "MASTER",
  remaster: "Re:MASTER",
  utage: "UTAGE",
};

export function Chip({ difficulty, level, constant, type }: { difficulty: string; level?: string; constant?: number; type?: string }) {
  const t = useTranslations("dash");
  const key = (difficulty || "master").toLowerCase();
  return (
    <span className={`chip chip-${key}`}>
      {TIER[key] ?? key.toUpperCase()}
      {level ? <b>{level}</b> : null}
      {constant ? <em title={t("chartConstant")}>{constant.toFixed(1)}</em> : null}
      {type ? <i>{type.toUpperCase()}</i> : null}
    </span>
  );
}

export function Jacket({ cover, size = 40 }: { cover: string; size?: number }) {
  const file = (cover || "").split("/").pop()?.split("?")[0] ?? "";
  if (!file) return <span className="jacket empty" style={{ width: size, height: size }} />;
  return <img className="jacket" src={`/api/jacket/${encodeURIComponent(file)}`} width={size} height={size} alt="" loading="lazy" />;
}

export function pct(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined) return "—";
  return `${value.toFixed(digits)}%`;
}

export function num(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return value.toLocaleString(activeTag());
}

export function when(iso: string | null | undefined): string {
  if (!iso) return activeT("dash")("never");
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString(activeTag(), { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

export function day(iso: string | null | undefined): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleDateString(activeTag(), { day: "numeric", month: "short" });
}

export function ago(iso: string | null | undefined): string {
  const t = activeT("dash");
  if (!iso) return t("never");
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return iso;
  const minutes = Math.round((Date.now() - then) / 60000);
  if (minutes < 2) return t("justNow");
  if (minutes < 60) return t("minAgo", { n: minutes });
  const hours = Math.round(minutes / 60);
  if (hours < 48) return t("hAgo", { n: hours });
  return t("daysAgo", { n: Math.round(hours / 24) });
}

export function Lamp({ fc, fs }: { fc: string; fs: string }) {
  const marks: string[] = [];
  if (fc && fc !== "NONE") marks.push(fc);
  if (fs && fs !== "NONE") marks.push(fs);
  if (!marks.length) return <span className="dim">—</span>;
  return <span className="lamp-text">{marks.join(" · ")}</span>;
}

export function Empty({ children }: { children: React.ReactNode }) {
  return <p className="empty">{children}</p>;
}

/** What a section shows when its data could not be fetched: the reason, and a way to try again. Never the empty-state copy. */
/** An error's words, with its error ID as a button that copies it: the support server asks for the ID, and selecting it by hand is fiddly on a phone. */
export function ErrorText({ message }: { message: string }) {
  const t = useTranslations("dash");
  const [copied, setCopied] = useState(false);
  const found = /\b[0-9A-F]{8}\b/.exec(message);
  if (!found) return <>{message}</>;
  const id = found[0];
  const copy = () => {
    navigator.clipboard
      ?.writeText(id)
      .then(() => {
        setCopied(true);
        setTimeout(() => setCopied(false), 1600);
      })
      .catch(() => undefined); // the ID is still there to select by hand
  };
  return (
    <>
      {message.slice(0, found.index)}
      <button type="button" className="linkish mono" onClick={copy} title={t("copyId")} aria-label={`${t("copyId")} ${id}`}>
        {copied ? t("copiedId") : id}
      </button>
      {message.slice(found.index + id.length)}
    </>
  );
}

export function LoadError({ what, message, onRetry }: { what: string; message: string; onRetry?: () => void }) {
  const t = useTranslations("dash");
  return (
    <p className="empty error" role="alert">
      {t.rich("couldntLoad", { what, message: () => <ErrorText message={message} /> })}
      {onRetry ? (
        <>
          {" "}
          <button type="button" className="linkish" onClick={onRetry}>
            {t("tryAgain")}
          </button>
        </>
      ) : null}{" "}
      <Support inline />
    </p>
  );
}

/** "3 days ago" that reveals the exact moment on hover and to assistive tech. */
export function Ago({ iso, prefix = "" }: { iso: string | null | undefined; prefix?: string }) {
  const t = useTranslations("dash");
  if (!iso) return <>{prefix}{t("never")}</>;
  return (
    <time dateTime={iso} title={when(iso)}>
      {prefix}
      {ago(iso)}
    </time>
  );
}

/** A small circled i that opens a short explanation of the section it sits beside. */
export function Info({ text }: { text: string }) {
  const t = useTranslations("dash");
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLSpanElement>(null);
  useDismiss(open, box, setOpen);
  return (
    <span className={`info${open ? " open" : ""}`} ref={box}>
      <button type="button" className="info-btn" aria-label={t("moreInfo")} aria-expanded={open} onClick={() => setOpen(!open)}>
        i
      </button>
      {open && (
        <span className="info-pop" role="tooltip">
          {text}
        </span>
      )}
    </span>
  );
}

export function Label({ children, info }: { children: React.ReactNode; info?: string }) {
  return (
    <div className="label">
      {children}
      {info ? <Info text={info} /> : null}
    </div>
  );
}

export type OpenChart = (title: string, type: string, difficulty: string) => void;

/** A chart title that opens the chart in the Look up tab. */
export function TitleLink({ title, type, difficulty, onOpen }: { title: string; type: string; difficulty: string; onOpen?: OpenChart }) {
  if (!onOpen) return <span className="title">{title}</span>;
  return (
    <button type="button" className="title title-link" onClick={() => onOpen(title, type, difficulty)}>
      {title}
    </button>
  );
}

export type ImageKind = "analyze" | "profile" | "new" | "traits" | "progress" | "best50" | "recent";

/** Saves the picture the matching Discord command draws. Rendering takes a moment, so it says so. */
/** `ready` is false until the bot holds a read of this player: until then there is nothing to draw, so the button waits instead of failing. */
export function SaveImage({ kind, ready = true }: { kind: ImageKind; ready?: boolean }) {
  const t = useTranslations("dash");
  const label = t(`images.${kind}`);
  const [state, setState] = useState<"" | "busy" | "empty" | "failed">("");

  const save = async () => {
    setState("busy");
    try {
      const answer = await fetch(`/api/me/image?kind=${encodeURIComponent(kind)}`, { credentials: "same-origin" });
      // 404 here means the bot had nothing to draw yet, which is not the same as a failure
      if (answer.status === 404) {
        setState("empty");
        return;
      }
      if (!answer.ok) throw new Error(String(answer.status));
      const blob = await answer.blob();
      const href = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = href;
      link.download = `rasmai-${kind}.png`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      // the browser needs the address to outlive the click, not the call
      setTimeout(() => URL.revokeObjectURL(href), 10_000);
      setState("");
    } catch {
      setState("failed");
    }
  };

  return (
    <button type="button" className={`save-image${ready ? "" : " waiting"}`} onClick={save} disabled={state === "busy" || !ready}
            title={ready ? t("saveTitle", { what: label }) : t("saveWaits")}>
      {state === "busy" ? t("makingImage")
        : state === "empty" ? t("noImageData")
        : state === "failed" ? t("imageFailed")
        : t("saveImage", { what: label })}
    </button>
  );
}
