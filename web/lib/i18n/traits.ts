import type { Locale } from "./index";
import { activeT } from "./active";

const JAPANESE = /[぀-ヿ㐀-鿿]/;

/** The bot's labels hold spaces, brackets and `&`, which a JSON key cannot: lower-case, and each run of anything but a-z and 0-9 becomes one `_` ("slow songs (under 130 BPM)" is `slow_songs_under_130_bpm`). */
export function traitKey(label: string): string {
  return label.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "");
}

/** A trait's name for the reader: an editor's Japanese tag as written, the bot's own names from the translation file. */
export function traitName(label: string, english: string | undefined, locale: Locale): string {
  if (locale !== "ja") return english || label;
  if (JAPANESE.test(label)) return label;
  const names = activeT("traitNames");
  for (const name of [label, english]) {
    const key = name && traitKey(name);
    if (key && names.has(key as never)) return names(key as never);
  }
  const root = activeT(undefined as never) as unknown as (key: string, values: Record<string, string>) => string;
  const by = /^charts by (.+)$/.exec(label);
  if (by) return root("chartsBy", { designer: by[1] });
  const notes = /^(tap|hold|slide|touch|break) notes$/.exec(label);
  if (notes) return root("noteTrait", { kind: noteKind(notes[1], locale) });
  return english || label;
}

/** A note type's name for the reader, in the page's language (callers may still pass it). */
export function noteKind(kind: string, _locale?: Locale): string {
  const names = activeT("noteKinds");
  return names.has(kind as never) ? names(kind as never) : kind;
}
