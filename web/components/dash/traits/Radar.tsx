import type { Axis } from "./rules";
import { BASELINE, isLean } from "./rules";

function textWidth(text: string): number {
  let cells = 0;
  for (const char of text) cells += char.codePointAt(0)! > 0x2e7f ? 2 : 1;
  return cells;
}

/** Split a label into at most two lines of roughly equal length, cutting a line that still overflows. */
function wrapLabel(text: string, width = 14): string[] {
  const cut = (line: string) => {
    if (textWidth(line) <= width + 4) return line;
    let kept = "";
    for (const char of line) {
      if (textWidth(kept + char) > width + 3) break;
      kept += char;
    }
    return kept.trimEnd() + "…";
  };
  if (textWidth(text) <= width) return [text];
  // a bracketed qualifier reads best whole on its own line
  const bracket = text.lastIndexOf(" (");
  if (bracket > 0 && text.endsWith(")")) {
    const name = text.slice(0, bracket);
    const qualifier = text.slice(bracket + 1);
    if (textWidth(name) <= width + 4 && textWidth(qualifier) <= width + 4) return [name, qualifier];
  }
  // an ampersand joins two names with no space around it, so it is a place to break as well
  const words = text.match(/\S+?[＆&]|\S+/g) ?? [text];
  // a lone ampersand stays with the word before it, so no line starts with one
  for (let i = words.length - 1; i > 0; i--) {
    if (words[i] === "&" || words[i] === "＆") words.splice(i - 1, 2, `${words[i - 1]} ${words[i]}`);
  }
  if (words.length < 2) return [cut(text)];
  let best: [string, string] | null = null;
  let bestScore = Infinity;
  for (let i = 1; i < words.length; i++) {
    const pair: [string, string] = [words.slice(0, i).join(" "), words.slice(i).join(" ")];
    const score = Math.max(textWidth(pair[0]), textWidth(pair[1]));
    if (score < bestScore) {
      best = pair;
      bestScore = score;
    }
  }
  return best!.map(cut);
}

/** The wheel itself. The middle ring is the player's own average; outward is stronger. A hollow point is a leaning trait. */
export function Radar({ axes }: { axes: Axis[] }) {
  const width = 520;
  const height = 420;
  const midX = width / 2;
  const midY = height / 2;
  const radius = midY - 72;
  const at = (i: number, reach: number) => {
    const angle = (2 * Math.PI * i) / axes.length;
    return [midX + radius * reach * Math.sin(angle), midY - radius * reach * Math.cos(angle)] as const;
  };
  const ring = (r: number) => axes.map((_, i) => at(i, r).join(",")).join(" ");
  const reachOf = (a: Axis) => Math.max(0.12, Math.min(1, 0.5 + a.offset / 2));
  const shape = axes.map((a, i) => at(i, reachOf(a)).join(",")).join(" ");
  const labelReach = (radius + 18) / radius;
  return (
    <svg className="radar" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="your traits against your own average">
      {[0.25, 0.5, 0.75, 1].map((r) => (
        <polygon key={r} points={ring(r)} className={r === 0.5 ? "ring mid" : "ring"} />
      ))}
      {axes.map((a, i) => {
        const [x, y] = at(i, 1);
        return <line key={a.label} x1={midX} y1={midY} x2={x} y2={y} className="spoke" />;
      })}
      <polygon points={shape} className="shape" />
      {axes.map((a, i) => {
        const [x, y] = at(i, reachOf(a));
        const [lx, ly] = at(i, labelReach);
        const sin = Math.sin((2 * Math.PI * i) / axes.length);
        const anchor = Math.abs(sin) < 0.35 ? "middle" : sin > 0 ? "start" : "end";
        const lines = wrapLabel(a.english ?? a.label);
        // the name and its value stack away from the wheel: above it at the top, below it at the
        // bottom, centred at the sides, so a two-line name never runs into its own point
        const block = (lines.length - 1) * 13 + 14;
        const firstY = ly - block / 2 - Math.cos((2 * Math.PI * i) / axes.length) * (block / 2);
        const valueY = firstY + block;
        return (
          <g key={a.label}>
            <circle cx={x} cy={y} r={isLean(a) || a.filler ? 4.5 : 4} className={isLean(a) || a.filler ? "dot lean" : "dot"} />
            {lines.map((line, row) => (
              <text key={row} x={lx} y={firstY + row * 13} textAnchor={anchor} className={`axis ${a.filler ? "even" : a.offset < 0 ? "down" : "up"}`}>
                {line}
              </text>
            ))}
            <text x={lx} y={valueY} textAnchor={anchor} className="axis-val">
              {a.offset > 0 ? "+" : ""}
              {a.offset.toFixed(2)}
              {isLean(a) || a.filler ? " ?" : ""}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
