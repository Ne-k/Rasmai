import re
from typing import Any, Dict, List, Sequence

from rasmai.scraping.mai_notes import english_label
from rasmai.images.posters import _esc, panel, rating_plate, stats
from rasmai.images.pages.common import _image


def _text_width(text: str) -> int:
    """How many character cells a label takes, counting East Asian characters as two."""
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


def _radar_svg(axes: Sequence[Dict[str, Any]], width: int = 1000, height: int = 780) -> str:
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
    count = len(axes)
    angles = [2 * math.pi * i / count for i in range(count)]
    # a name over its point at the top, beside it at the side, under it low on the wheel, leaning outward when the point is off the middle
    under = [math.cos(a) < -0.45 for a in angles]
    beside = [not low and abs(math.sin(a)) >= 0.35 for a, low in zip(angles, under)]
    low_edge = max(-math.cos(a) for a in angles)
    top_room, bottom_room, name_width = 120, 118 if any(under) else 40, 190
    # the wheel takes all the room its names leave, so three axes draw as large a ring as eight
    reach_side = [(width / 2 - name_width - (34 if side else 0)) / abs(math.sin(a)) for a, side, low in zip(angles, beside, under)
                  if side or (low and abs(math.sin(a)) >= 0.35)]
    radius = min([(height - top_room - bottom_room) / (1 + low_edge)] + reach_side)
    mid_x = width / 2
    mid_y = top_room + radius + (height - top_room - bottom_room - radius * (1 + low_edge)) / 2

    def ring(scale: float) -> str:
        return " ".join(f"{mid_x + radius * scale * math.sin(a):.1f},{mid_y - radius * scale * math.cos(a):.1f}" for a in angles)

    # the rim is Rasmai's ring: a thick ink band with a line of paper run along it, round a plate the shape is drawn on
    parts: List[str] = [f'<polygon points="{ring(1.0)}" class="pg-rim"/><polygon points="{ring(1.0)}" class="pg-rim-in"/>',
                        f'<polygon points="{ring(0.75)}" class="pg-ring"/><polygon points="{ring(0.25)}" class="pg-ring"/>',
                        f'<polygon points="{ring(0.5)}" class="pg-ring mid"/>']
    shape: List[str] = []
    marks: List[str] = []
    for index, axis in enumerate(axes):
        angle = angles[index]
        # the middle ring is nothing to say; a point a full point above their own middle reaches the edge
        reach = max(0.12, min(1.0, 0.5 + float(axis["offset"]) / 2.0))
        x, y = mid_x + radius * reach * math.sin(angle), mid_y - radius * reach * math.cos(angle)
        shape.append(f"{x:.1f},{y:.1f}")
        edge_x, edge_y = mid_x + radius * math.sin(angle), mid_y - radius * math.cos(angle)
        parts.append(f'<line x1="{mid_x}" y1="{mid_y}" x2="{edge_x:.1f}" y2="{edge_y:.1f}" class="pg-ring"/>')
        lines = _wrap_label(english_label(str(axis["label"])))
        lean = "" if axis.get("filler") else (" down" if float(axis["offset"]) < 0 else " up")
        hollow = " hollow" if axis.get("filler") or (axis.get("leaning") and not axis.get("verified")) else ""
        marks.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="15" class="pg-vertex{lean}{hollow}"/>')
        block = len(lines) * 27 + 26
        outward = 1 if math.sin(angle) > 0 else -1
        if beside[index]:
            anchor, label_x, top = ("start" if outward > 0 else "end"), edge_x + 30 * outward, edge_y - block / 2
        elif under[index] and abs(math.sin(angle)) >= 0.35:
            anchor, label_x, top = ("start" if outward > 0 else "end"), edge_x - 14 * outward, edge_y + 28
        else:
            anchor, label_x = "middle", edge_x
            top = edge_y + 30 if under[index] else edge_y - 30 - block
        for row, line in enumerate(lines):
            parts.append(f'<text x="{label_x:.1f}" y="{top + 13 + row * 27:.1f}" text-anchor="{anchor}" dominant-baseline="middle" '
                         f'class="pg-axis-name{lean}">{_esc(line)}</text>')
        parts.append(f'<text x="{label_x:.1f}" y="{top + 13 + len(lines) * 27:.1f}" text-anchor="{anchor}" dominant-baseline="middle" '
                     f'class="pg-axis-value{lean}">{float(axis["offset"]):+.2f}</text>')
    parts.append(f'<polygon points="{" ".join(shape)}" class="pg-shape"/>')
    return f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">{"".join(parts + marks)}</svg>'


def traits_image_html(axes: Sequence[Dict[str, Any]], weak: Sequence[Dict[str, Any]], strong: Sequence[Dict[str, Any]],
                      player_name: str, rating: int, avatar_b64: str, charts: int, date_text: str = "",
                      summary: Sequence[str] = (), judgements: Sequence[str] = ()) -> str:
    """The wheel in its own panel between what the player loses points on and what they shine at, and what was counted in the banner over them.

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
    :param summary: How many traits are confirmed, leaning and level: the embed's own clauses, one each.
    :type summary: Sequence[str]
    :param judgements: What the judgement pages say, a line each, as the embed words it.
    :type judgements: Sequence[str]
    :rtype: str
    """
    scale = max([1.0] + [abs(float(item["offset"])) for item in [*weak, *strong]])

    def rows(items: Sequence[Dict[str, Any]], tone: str) -> str:
        out = ""
        for item in items:
            label = _esc(english_label(str(item["label"])))
            mark = "" if item.get("verified") else (", leaning" if item.get("leaning") else ", watching")
            off = float(item["offset"])
            out += (f'<div class="pg-trait pg-tk {tone}{"" if item.get("verified") else " unsure"}"><b>{off:+.2f}</b>'
                    f'<div class="pg-trait-what"><span>{label}</span><small>{item["count"]} '
                    f'{"play" if item.get("dimension") == "judgement" else "chart"}{"" if item["count"] == 1 else "s"}{mark}</small>'
                    f'<div class="pg-bar"><i style="width:{abs(off) / scale * 100:.0f}%"></i></div></div></div>')
        return out or '<div class="pg-trait pg-tk none">nothing stands out yet</div>'

    def bold(text: str) -> str:
        # the embed's own wording, its bold kept: escaped first, so only our own marks become tags
        return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", _esc(text))

    counted = ", ".join(bold(piece) for piece in summary)
    judged = "".join(f"<p>{bold(text)}</p>" for text in judgements)
    banner = ('<div class="banner pg-banner">' + stats([("Charts", _esc(charts)), ("Weak spots", _esc(len(weak))), ("Strengths", _esc(len(strong)))])
              + (f'<p class="pg-facts">{counted}</p>' if counted else "")
              + (f'<div class="pg-judged"><h3>Judgements, measured</h3>{judged}</div>' if judged else "") + "</div>")
    # one key for the wheel and both lists, under the wheel
    wheel = f"""<div class="pg-wheel">{_radar_svg(axes)}</div>
        <div class="pg-wheel-key"><p>Ring: your average. Further out: stronger. Hollow point: not sure yet.</p>
          <p>Stub: points under or over your curve <i class="pg-bar"><i></i></i>confirmed <i class="pg-bar unsure"><i></i></i>not sure yet</p></div>"""
    lose = panel("cyan run pg-list", "Where you lose points", rows(weak, "down"), "below your curve")
    gain = panel("pink run pg-list", "Where you're strong", rows(strong, "up"), "above your curve")
    # a few traits in all stack both lists beside the wheel, so neither sheet is left mostly empty; more stand either side of it
    if len(weak) + len(strong) <= 6:
        board = f'<div class="pg-traits pg-stacked">{panel("purple pg-wheel-panel", "Trait wheel", wheel, "points against your own curve")}<div class="pg-lists">{lose}{gain}</div></div>'
    else:
        board = f'<div class="pg-traits">{lose}{panel("purple pg-wheel-panel", "Trait wheel", wheel, "points against your own curve")}{gain}</div>'
    body = banner + board
    return _image("Your traits", player_name, avatar_b64, rating_plate(rating), "rating", body, date_text)
