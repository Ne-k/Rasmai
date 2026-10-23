// Chart folders picked from the visitor's own device: every folder holding a maidata.txt becomes a song.  Nothing is uploaded.
import { parseMaidata } from "./chart.mjs";
import { SLOT_NAMES } from "./build.mjs";
import type { Maidata } from "./types";

export type SongChart = { slot: number; name: string; level: string | null; designer: string | null };
export type Song = {
  id: string;
  title: string;
  artist: string;
  bpm: number | null;
  group: string;             // the folder above the song's folder, for libraries sorted into version folders
  charts: SongChart[];
  audio: File | null;
  image: File | null;
  maidata: Maidata;
  added: number;             // order of import, for "recently added"
};

const AUDIO = /^(track|music|audio|song)\.(mp3|ogg|wav|m4a|aac|opus|flac)$/i;
const IMAGE = /^(bg|jacket|cover|bg_?image)\.(jpg|jpeg|png|webp)$/i;

/** Songs from a list of files that carry paths (an <input webkitdirectory> pick, or files gathered from a drop). */
export async function songsFromFiles(files: { file: File; path: string }[]): Promise<Song[]> {
  const byDir = new Map<string, { file: File; name: string }[]>();
  for (const { file, path } of files) {
    const cut = path.lastIndexOf("/");
    const dir = cut < 0 ? "" : path.slice(0, cut);
    const name = cut < 0 ? path : path.slice(cut + 1);
    (byDir.get(dir) ?? byDir.set(dir, []).get(dir)!).push({ file, name });
  }
  const songs: Song[] = [];
  let added = 0;
  for (const [dir, entries] of byDir) {
    const md = entries.find((e) => e.name === "maidata.txt");
    if (!md) continue;
    let parsed: Maidata;
    try {
      parsed = parseMaidata(await md.file.text());
    } catch {
      continue;
    }
    const charts = Object.values(parsed.charts)
      .filter((c) => c.inote.trim())
      .map((c) => ({ slot: c.slot, name: SLOT_NAMES[c.slot] ?? `#${c.slot}`, level: c.level, designer: c.designer }))
      .sort((a, b) => a.slot - b.slot);
    if (!charts.length) continue;
    const parts = dir.split("/");
    songs.push({
      id: dir || md.file.name,
      title: parsed.meta.title.trim() || parts[parts.length - 1] || "untitled",
      artist: parsed.meta.artist,
      bpm: parsed.meta.wholebpm,
      group: parts.length > 2 ? parts[parts.length - 2] : "",
      charts,
      audio: entries.find((e) => AUDIO.test(e.name))?.file ?? null,
      image: entries.find((e) => IMAGE.test(e.name))?.file ?? null,
      maidata: parsed,
      added: added++,
    });
  }
  return songs.sort((a, b) => a.title.localeCompare(b.title));
}

/** Every file under a dropped folder, with its path; falls back to the plain files of a drop without folders. */
export async function filesFromDrop(items: DataTransferItemList): Promise<{ file: File; path: string }[]> {
  const out: { file: File; path: string }[] = [];
  const walk = async (entry: FileSystemEntry, path: string): Promise<void> => {
    if (entry.isFile) {
      const file = await new Promise<File>((ok, no) => (entry as FileSystemFileEntry).file(ok, no));
      out.push({ file, path: path + entry.name });
    } else if (entry.isDirectory) {
      const reader = (entry as FileSystemDirectoryEntry).createReader();
      for (;;) {
        const batch = await new Promise<FileSystemEntry[]>((ok, no) => reader.readEntries(ok, no));
        if (!batch.length) break;
        for (const e of batch) await walk(e, path + entry.name + "/");
      }
    }
  };
  const entries = Array.from(items).map((i) => i.webkitGetAsEntry?.() ?? null);
  for (const e of entries) if (e) await walk(e, "");
  if (!out.length) for (const i of Array.from(items)) { const f = i.getAsFile(); if (f) out.push({ file: f, path: f.name }); }
  return out;
}

/** The same shape from a folder input's FileList (webkitRelativePath carries the path). */
export function filesFromInput(list: FileList): { file: File; path: string }[] {
  return Array.from(list).map((file) => ({ file, path: file.webkitRelativePath || file.name }));
}

/** "13.7" -> 13.7, "13+" -> 13.6, "13" -> 13, "?" -> null: the number sorting and filtering go by. */
export function levelValue(level: string | null): number | null {
  if (!level) return null;
  const m = /^(\d+)(?:\.(\d))?(\+)?/.exec(level.trim());
  if (!m) return null;
  return Number(m[1]) + (m[2] ? Number(m[2]) / 10 : m[3] ? 0.6 : 0);
}
