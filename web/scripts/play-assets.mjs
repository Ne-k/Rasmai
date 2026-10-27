// Copies the chart player's optional game assets (note sprites and sound effects) into web/public/play from a maimai-dx
// extraction (its public/ folder: skin/ from extract-skin.mjs, se/ from extract-voices.mjs, data/seoptions.json).
// Without them the player draws plain shapes and plays no effects.
//   node scripts/play-assets.mjs <maimai-dx/public>
import fs from "node:fs";
import path from "node:path";

const [src] = process.argv.slice(2);
if (!src) { console.error("usage: node scripts/play-assets.mjs <maimai-dx/public>"); process.exit(1); }
const out = path.join(path.dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1")), "..", "public", "play");

// sprites: every gameplay sheet in the manifest (the menu art under ui/ is not used here)
const manifest = JSON.parse(fs.readFileSync(path.join(src, "skin", "manifest.json"), "utf8"));
const kept = {};
let sprites = 0;
for (const [name, meta] of Object.entries(manifest)) {
  if (name.startsWith("ui/")) continue;
  const from = path.join(src, "skin", name + ".png"), to = path.join(out, "skin", name + ".png");
  if (!fs.existsSync(from)) continue;
  fs.mkdirSync(path.dirname(to), { recursive: true });
  fs.copyFileSync(from, to);
  kept[name] = meta;
  sprites++;
}
// the fan slide's stripes and break glow live in the SlideFan prefab's own sprite folder of the Unity export, not in skin/
const fanDir = path.join(src, "ui", "sprites", "process", "game", "sprites", "slidefan");
if (fs.existsSync(fanDir)) {
  fs.mkdirSync(path.join(out, "skin", "fan"), { recursive: true });
  for (const f of fs.readdirSync(fanDir)) {
    if (!/^(MM_UI_Game_0(5[3-9]|6[0-3])|SlideFun_Eff_\d\d)\.png$/.test(f)) continue;
    const buf = fs.readFileSync(path.join(fanDir, f));
    fs.writeFileSync(path.join(out, "skin", "fan", f), buf);
    // PNG: width and height are the big-endian ints at bytes 16 and 20
    kept["fan/" + f.slice(0, -4)] = { w: buf.readUInt32BE(16), h: buf.readUInt32BE(20), px: 0.5, py: 0.5 };
    sprites++;
  }
}
fs.writeFileSync(path.join(out, "skin", "manifest.json"), JSON.stringify(kept));

// sounds: the in-play effects (SE_GAME_*) and the option table that names the choosable sets
let sounds = 0;
const seDir = path.join(src, "se", "Mai2Cue");
fs.mkdirSync(path.join(out, "se", "Mai2Cue"), { recursive: true });
for (const f of fs.readdirSync(seDir)) if (/^SE_GAME_.*\.mp3$/.test(f)) { fs.copyFileSync(path.join(seDir, f), path.join(out, "se", "Mai2Cue", f)); sounds++; }
fs.copyFileSync(path.join(src, "data", "seoptions.json"), path.join(out, "se", "seoptions.json"));
console.log(`copied ${sprites} sprites and ${sounds} sounds to ${out}`);
