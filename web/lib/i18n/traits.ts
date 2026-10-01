import type { Locale } from "./index";
import { messages } from "./messages";

const JAPANESE = /[\u3040-\u30ff\u3400-\u9fff]/;

/** A trait's name for the reader: an editor's Japanese tag as written, the bot's own names from the translation file. */
export function traitName(label: string, english: string | undefined, locale: Locale): string {
  if (locale !== "ja") return english || label;
  const names = messages.ja.traitNames;
  if (JAPANESE.test(label)) return label;
  const known = names[label] ?? (english ? names[english] : undefined);
  if (known) return known;
  const by = /^charts by (.+)$/.exec(label);
  if (by) return messages.ja.chartsBy(by[1]);
  const notes = /^(tap|hold|slide|touch|break) notes$/.exec(label);
  if (notes) return messages.ja.noteTrait(messages.ja.noteKinds[notes[1]]);
  return english || label;
}

/** A note type's name for the reader. */
export function noteKind(kind: string, locale: Locale): string {
  return messages[locale].noteKinds[kind] ?? kind;
}
