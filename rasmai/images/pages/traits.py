import re
from typing import Any, Dict, List, Sequence

from rasmai.scraping.mai_notes import english_label
from rasmai.images.posters import _esc
from rasmai.images.pages.common import _image


def _text_width(text: str) -> int:
    """How many character cells a label takes, counting East Asian characters as two.

    :param text: The label.
    :type text: str
    :rtype: int
    """
    return sum(2 if ord(char) > 0x2E7F else 1 for char in text)


def _wrap_label(text: str, width: int = 14) -> List[str]:
    """Split a radar label into at most two lines of roughly equal length.

    A label that fits stays on one line. Otherwise the break between words that keeps the longer
    line shortest is used, and a line that still overflows is cut with an ellipsis rather than
    running under the neighbouring text.

    :param text: The label in English.
    :type text: str
    :param width: The most character cells a line should take.
    :type width: int
    :rtype: List[str]
    """
    def cut(line: str) -> str:
        if _text_width(line) <= width + 4:
            return line
        kept = ""
        for char in line:
            if _text_width(kept + char) > width + 3:
                break
            kept += char
        return kept.rstrip() + "…"

    if _text_width(text) <= width:
        return [text]
    # a bracketed qualifier reads best whole on its own line
    if " (" in text and text.endswith(")"):
        name, _, qualifier = text.rpartition(" (")
        if _text_width(name) <= width + 4 and _text_width(qualifier) + 1 <= width + 4:
            return [name, "(" + qualifier]
    # an ampersand joins two names with no space around it, so it is a place to break as well
    words = re.findall(r"\S+?[＆&]|\S+", text)
    # a lone ampersand stays with the word before it, so no line starts with one
    for position in range(len(words) - 1, 0, -1):
        if words[position] in ("&", "＆"):
            words[position - 1:position + 1] = [words[position - 1] + " " + words[position]]
    if len(words) < 2:
        return [cut(text)]
    best = min(((" ".join(words[:i]), " ".join(words[i:])) for i in range(1, len(words))),
               key=lambda pair: max(_text_width(pair[0]), _text_width(pair[1])))
    return [cut(best[0]), cut(best[1])]


def _radar_svg(axes: Sequence[Dict[str, Any]], width: int = 680, height: int = 540) -> str:
    """A radar of the player's traits: the middle ring is their own average, outward is stronger.

    Not a groove radar and not modelled on one; the axes are whichever of the player's own
    chart traits carry the most signal, and the scale is points against their own curve.

    :param axes: The traits the wheel is drawn on.
    :type axes: Sequence[Dict[str, Any]]
    :param width: How wide to draw, in pixels. Wider than tall, so the labels at the sides have room.
    :type width: int
    :param height: How tall to draw, in pixels.
    :type height: int
    :rtype: str
    """
    import math
    if len(axes) < 3:
        return ""
    mid_x, mid_y, radius = width / 2, height / 2, height / 2 - 95
    parts: List[str] = []
    for ring in (0.25, 0.5, 0.75, 1.0):
        points = " ".join(
            f"{mid_x + radius * ring * math.sin(2 * math.pi * i / len(axes)):.1f},{mid_y - radius * ring * math.cos(2 * math.pi * i / len(axes)):.1f}"
            for i in range(len(axes)))
        stroke = "2" if ring == 0.5 else "1"
        colour = "#5f5b52" if ring == 0.5 else "#2b2924"
        parts.append(f'<polygon points="{points}" fill="none" stroke="{colour}" stroke-width="{stroke}"/>')
    shape: List[str] = []
    hollow: List[bool] = []
    for index, axis in enumerate(axes):
        angle = 2 * math.pi * index / len(axes)
        # the middle ring is nothing to say; a point a full point above their own middle reaches the edge
        reach = max(0.12, min(1.0, 0.5 + float(axis["offset"]) / 2.0))
        x, y = mid_x + radius * reach * math.sin(angle), mid_y - radius * reach * math.cos(angle)
        shape.append(f"{x:.1f},{y:.1f}")
        hollow.append(bool(axis.get("filler") or (axis.get("leaning") and not axis.get("verified"))))
        edge_x, edge_y = mid_x + radius * math.sin(angle), mid_y - radius * math.cos(angle)
        parts.append(f'<line x1="{mid_x}" y1="{mid_y}" x2="{edge_x:.1f}" y2="{edge_y:.1f}" stroke="#2b2924" stroke-width="1"/>')
        label_x, label_y = mid_x + (radius + 24) * math.sin(angle), mid_y - (radius + 24) * math.cos(angle)
        anchor = "middle" if abs(math.sin(angle)) < 0.35 else ("start" if math.sin(angle) > 0 else "end")
        lines = _wrap_label(english_label(str(axis["label"])))
        colour = "#9b968a" if axis.get("filler") else ("#ff3d8f" if float(axis["offset"]) < 0 else "#f0c04a")
        # the name and its value stack away from the wheel: above it at the top, below it at the
        # bottom, centred at the sides, so a two-line name never runs into its own point
        block = (len(lines) - 1) * 18 + 19
        first_y = label_y - block / 2 - math.cos(angle) * block / 2
        for row, line in enumerate(lines):
            parts.append(f'<text x="{label_x:.1f}" y="{first_y + row * 18:.1f}" text-anchor="{anchor}" dominant-baseline="middle" '
                         f'font-family="Segoe UI,Inter,sans-serif" font-size="16" fill="{colour}">{_esc(line)}</text>')
        value_y = first_y + block
        parts.append(f'<text x="{label_x:.1f}" y="{value_y:.1f}" text-anchor="{anchor}" dominant-baseline="middle" '
                     f'font-family="Cascadia Mono,Consolas,monospace" font-size="13" fill="#9b968a">{float(axis["offset"]):+.2f}</text>')
    parts.append(f'<polygon points="{" ".join(shape)}" fill="rgba(92,211,232,0.22)" stroke="#5cd3e8" stroke-width="3" stroke-linejoin="round"/>')
    for point, lean in zip(shape, hollow):
        x, y = point.split(",")
        if lean:
            parts.append(f'<circle cx="{x}" cy="{y}" r="5" fill="#15140f" stroke="#5cd3e8" stroke-width="2.5"/>')
        else:
            parts.append(f'<circle cx="{x}" cy="{y}" r="4.5" fill="#5cd3e8"/>')
    return f'<svg viewBox="0 0 {width} {height}" width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">{"".join(parts)}</svg>'


def traits_image_html(axes: Sequence[Dict[str, Any]], weak: Sequence[Dict[str, Any]], strong: Sequence[Dict[str, Any]],
                      player_name: str, rating: int, avatar_b64: str, charts: int, date_text: str = "") -> str:
    """The radar beside the two lists: what the player loses points on and what they shine at.

    :param axes: The traits the wheel is drawn on.
    :type axes: Sequence[Dict[str, Any]]
    :param player_name: The player's name on maimai DX NET.
    :type player_name: str
    :param rating: The player's rating.
    :type rating: int
    :param avatar_b64: The player's avatar, base64 encoded.
    :type avatar_b64: str
    :param charts: The charts to work through.
    :type charts: int
    :param date_text: The date to print on the image.
    :type date_text: str
    :param weak: The traits the player loses points on.
    :type weak: Sequence[Dict[str, Any]]
    :param strong: The traits the player gains on.
    :type strong: Sequence[Dict[str, Any]]
    :rtype: str
    """
    def rows(items: Sequence[Dict[str, Any]], tone: str) -> str:
        out = ""
        for item in items:
            label = _esc(english_label(str(item["label"])))
            mark = "" if item.get("verified") else " · leaning"
            out += (f'<div class="trait-row"><span class="trait-off {tone}">{float(item["offset"]):+.2f}</span>'
                    f'<span class="trait-name">{label}</span><span class="trait-n">{item["count"]}{mark}</span></div>')
        return out or '<div class="trait-none">nothing stands out yet</div>'

    body = f"""
    <div class="two-col">
      <div class="chart-wrap radar">{_radar_svg(axes)}
        <div class="legend"><span>middle ring = your own average</span><span>outward = stronger</span><span>hollow point = leaning or level with the rest, not confirmed</span></div>
      </div>
      <div>
        <div class="section-label">Where you lose points</div>
        {rows(weak, "down")}
        <div class="section-label">Where you shine</div>
        {rows(strong, "up")}
      </div>
    </div>"""
    counters = [("Charts", str(charts)), ("Weak spots", str(len(weak))), ("Strengths", str(len(strong)))]
    return _image("Your traits", player_name, avatar_b64, counters, str(rating), "rating", body, date_text)
