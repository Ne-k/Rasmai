from datetime import datetime
from typing import Any, Dict, List, Sequence, Tuple

from rasmai.images.posters import _esc, mark, panel, rating_plate, stats
from rasmai.images.pages.common import _image


def _progress_svg(points: Sequence[Dict[str, Any]], width: int = 2290, height: int = 760) -> str:
    stamps: List[datetime] = []
    for p in points:
        try:
            stamps.append(datetime.fromisoformat(str(p["recorded_at"])))
        except ValueError:
            stamps.append(datetime.now())
    ratings = [int(p["rating"]) for p in points]
    totals = [int(p["best50"]) for p in points]
    # the right margin holds the plate with the latest rating, past the end of the line
    ml, mr, mt, mb = 120, 250, 40, 58
    pw, ph = width - ml - mr, height - mt - mb
    t0, t1 = stamps[0], stamps[-1]
    span = max(1.0, (t1 - t0).total_seconds())
    lo = min(ratings + totals)
    hi = max(ratings + totals)
    pad = max(50, (hi - lo) // 8)
    y0, y1 = lo - pad, hi + pad

    def X(t: datetime) -> float:
        return ml + (t - t0).total_seconds() / span * pw

    def Y(v: float) -> float:
        return mt + (y1 - v) / max(1, y1 - y0) * ph

    parts: List[str] = []
    step = max(50, int(round((y1 - y0) / 6 / 50.0)) * 50)
    v = (y0 // step + 1) * step
    while v < y1:
        parts.append(f'<line x1="{ml}" y1="{Y(v):.1f}" x2="{width - mr + 40}" y2="{Y(v):.1f}" class="ch-grid"/>')
        parts.append(f'<text x="{ml - 30}" y="{Y(v) + 7:.1f}" text-anchor="end" class="ch-axis">{v}</text>')
        v += step
    labels = min(8, len(points))
    placed: List[float] = []
    # from the latest reading back, so today's date is always printed and a reading a few days before it gives way
    for index in sorted({int(i * (len(points) - 1) / max(1, labels - 1)) for i in range(labels)}, reverse=True):
        x = X(stamps[index])
        if all(abs(x - other) >= 110 for other in placed):
            placed.append(x)
            parts.append(f'<text x="{x:.1f}" y="{height - mb + 38}" text-anchor="middle" class="ch-axis">{stamps[index].day} {stamps[index]:%b}</text>')
    total_line = " ".join(f"{X(t):.1f},{Y(v):.1f}" for t, v in zip(stamps, totals))
    rating_line = " ".join(f"{X(t):.1f},{Y(v):.1f}" for t, v in zip(stamps, ratings))
    floor = height - mb
    parts.append(f'<polygon points="{ml},{floor} {rating_line} {X(t1):.1f},{floor}" class="ch-band"/>')
    for milestone in range((y0 // 1000 + 1) * 1000, y1, 1000):
        # a thousand is a line across with its figure on a gold tag at the left
        label = f"{milestone:,}"
        wide = 30 + 14 * len(label)
        parts.append(f'<line x1="{ml}" y1="{Y(milestone):.1f}" x2="{width - mr + 40}" y2="{Y(milestone):.1f}" class="pg-thousand"/>'
                     f'<rect x="{ml + 10}" y="{Y(milestone) - 46:.1f}" width="{wide}" height="36" rx="8" class="pg-tag"/>'
                     f'<text x="{ml + 10 + wide / 2}" y="{Y(milestone) - 20:.1f}" text-anchor="middle" class="pg-tag-text">{label}</text>')
    parts.append(f'<polyline points="{total_line}" class="pg-total"/>')
    parts.append(f'<polyline points="{rating_line}" class="pg-key"/><polyline points="{rating_line}" class="pg-line"/>')
    # a marker a reading while they can be told apart; a long history is the line alone
    if len(points) <= 60:
        for t, v in zip(stamps, ratings):
            parts.append(f'<circle cx="{X(t):.1f}" cy="{Y(v):.1f}" r="13" class="pg-dot"/><circle cx="{X(t):.1f}" cy="{Y(v):.1f}" r="5" class="pg-pip"/>')
    else:
        parts.append(f'<circle cx="{X(t1):.1f}" cy="{Y(ratings[-1]):.1f}" r="13" class="pg-dot"/><circle cx="{X(t1):.1f}" cy="{Y(ratings[-1]):.1f}" r="5" class="pg-pip"/>')
    svg = f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">{"".join(parts)}</svg>'
    # the plate is the kit's, laid over the graph at the end of the line; the SVG scales to its box, so a share of the box is a share of the drawing
    left = (X(t1) + 26) / width * 100
    top = min(max(Y(ratings[-1]), mt + 40), floor - 40) / height * 100
    return f'<div class="pg-graph">{svg}<div class="pg-now" style="left:{left:.2f}%;top:{top:.2f}%">{rating_plate(ratings[-1], small=True)}</div></div>'


def progress_image_html(points: Sequence[Dict[str, Any]], deltas: Sequence[Tuple[str, str]], player_name: str,
                        avatar_b64: str, date_text: str = "",
                        forecast: Sequence[Tuple[str, str, str]] = ()) -> str:
    def tone(value: str) -> str:
        return "down" if value.startswith("-") else "" if value.strip("+0") == "" else "up"

    def shift(label: str, value: str) -> str:
        way = tone(str(value))
        return f'<div class="pg-shift {way}"><span>{_esc(label)}</span><b>{mark(way) if way else ""}{_esc(value)}</b></div>'

    first = points[0]
    last = points[-1]
    try:
        began = datetime.fromisoformat(str(first["recorded_at"]))
        since = f"since {began.day} {began:%b}"
    except ValueError:
        since = "since first reading"
    figures = [("Rating", rating_plate(last["rating"], small=True)), ("First reading", _esc(first["rating"])),
               ("Plays since", _esc(int(last["plays"]) - int(first["plays"]))), ("New", _esc(last["new_total"])), ("Old", _esc(last["old_total"])),
               ("Best 50", _esc(last["best50"]))]
    shifts = f'<div class="pg-shifts">{"".join(shift(k, v) for k, v in deltas)}</div>' if deltas else ""
    ahead = ('<div class="pg-aheads"><h3>At this pace</h3>'
             + "".join(f'<div class="pg-ahead"><span>{_esc(k)}</span><b>{_esc(v)}</b><small>{_esc(s)}</small></div>' for k, v, s in forecast)
             + "</div>") if forecast else ""
    graph = f"""{_progress_svg(points)}
      <div class="pg-legend"><span><i class="rating"></i>rating</span><span><i class="total"></i>best-50 sum</span><span><i class="mark"></i>each 1,000</span></div>"""
    body = (f'<div class="banner pg-banner">{stats(figures)}{shifts}{ahead}</div>'
            + panel("pink pg-rise", "Rating over time", graph, f"{len(points)} reading{'' if len(points) == 1 else 's'}"))
    return _image("Progress", player_name, avatar_b64, f"{int(last['rating']) - int(first['rating']):+d}", since, body, date_text)
