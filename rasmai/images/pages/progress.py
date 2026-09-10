from datetime import datetime
from typing import Any, Dict, List, Sequence, Tuple

from rasmai.images.posters import _esc
from rasmai.images.pages.common import _image


def _progress_svg(points: Sequence[Dict[str, Any]], width: int = 2296, height: int = 640) -> str:
    stamps: List[datetime] = []
    for p in points:
        try:
            stamps.append(datetime.fromisoformat(str(p["recorded_at"])))
        except ValueError:
            stamps.append(datetime.now())
    ratings = [int(p["rating"]) for p in points]
    totals = [int(p["best50"]) for p in points]
    ml, mr, mt, mb = 90, 30, 30, 50
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
        parts.append(f'<line x1="{ml}" y1="{Y(v):.1f}" x2="{width - mr}" y2="{Y(v):.1f}" stroke="#2b2924"/>')
        parts.append(f'<text x="{ml - 10}" y="{Y(v) + 4:.1f}" text-anchor="end" font-family="Cascadia Mono,Consolas,monospace" font-size="12" fill="#9b968a">{v}</text>')
        v += step
    for milestone in range((y0 // 1000 + 1) * 1000, y1, 1000):
        parts.append(f'<line x1="{ml}" y1="{Y(milestone):.1f}" x2="{width - mr}" y2="{Y(milestone):.1f}" stroke="#5cd3e8" stroke-dasharray="6 6" opacity="0.6"/>')
    labels = min(8, len(points))
    for i in range(labels):
        t = stamps[int(i * (len(points) - 1) / max(1, labels - 1))]
        parts.append(f'<text x="{X(t):.1f}" y="{height - mb + 24}" text-anchor="middle" font-family="Cascadia Mono,Consolas,monospace" font-size="12" fill="#9b968a">{t.strftime("%d %b")}</text>')
    total_line = " ".join(f"{X(t):.1f},{Y(v):.1f}" for t, v in zip(stamps, totals))
    rating_line = " ".join(f"{X(t):.1f},{Y(v):.1f}" for t, v in zip(stamps, ratings))
    parts.append(f'<polyline points="{total_line}" fill="none" stroke="#9b968a" stroke-width="2" stroke-dasharray="4 5"/>')
    parts.append(f'<polyline points="{rating_line}" fill="none" stroke="#f0c04a" stroke-width="3"/>')
    for t, v in zip(stamps, ratings):
        parts.append(f'<circle cx="{X(t):.1f}" cy="{Y(v):.1f}" r="5" fill="#f0c04a"/>')
    last = points[-1]
    parts.append(f'<text x="{X(stamps[-1]) - 10:.1f}" y="{Y(ratings[-1]) - 12:.1f}" text-anchor="end" font-family="Cascadia Mono,Consolas,monospace" font-size="16" font-weight="700" fill="#f0c04a">{last["rating"]}</text>')
    return f'<svg viewBox="0 0 {width} {height}" width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">{"".join(parts)}</svg>'


def progress_image_html(points: Sequence[Dict[str, Any]], deltas: Sequence[Tuple[str, str]], player_name: str,
                        rating: int, avatar_b64: str, date_text: str = "",
                        forecast: Sequence[Tuple[str, str, str]] = ()) -> str:
    tiles = "".join(f'<div class="tile"><div class="k">{_esc(k)}</div><div class="v">{_esc(v)}</div></div>' for k, v in deltas)
    outlook = ""
    if forecast:
        cells = "".join(f'<div class="tile"><div class="k">{_esc(k)}</div><div class="v">{_esc(v)}</div><div class="s">{_esc(s)}</div></div>'
                        for k, v, s in forecast)
        outlook = f"""
    <div class="section-label">At this pace</div>
    <div class="tiles" style="grid-template-columns: repeat({max(1, len(forecast))}, 1fr)">{cells}</div>"""
    body = f"""
    <div class="section-label">Rating over time · {len(points)} readings</div>
    <div class="chart-wrap">{_progress_svg(points)}
      <div class="legend"><span><i style="background:#f0c04a"></i>rating</span><span><i style="background:#9b968a"></i>best-50 total as computed</span><span><i style="background:#5cd3e8"></i>thousands</span></div></div>
    <div class="section-label">Change</div>
    <div class="tiles" style="grid-template-columns: repeat({max(1, len(deltas))}, 1fr)">{tiles}</div>{outlook}"""
    first = points[0]
    counters = [("First reading", str(first["rating"])), ("Plays since", str(int(points[-1]["plays"]) - int(first["plays"])))]
    return _image("Progress", player_name, avatar_b64, counters, f"{int(points[-1]['rating']) - int(first['rating']):+d}", "since first reading", body, date_text)
