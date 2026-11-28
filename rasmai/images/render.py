from datetime import datetime
from pathlib import Path
from playwright.async_api import async_playwright
from typing import List, Dict, Optional, Any
import asyncio
import base64
import logging
import math

from rasmai.config import RENDERER
from rasmai.engine import analysis
from rasmai.images.posters import _esc, _page, _plays, kind_mark, mark, panel, rank_mark, rating_plate, stats, tier, tier_mark
from rasmai.storage.models import Recommendation

logger = logging.getLogger(__name__)


def _load_local_jacket(cover_url: str, jacket_path: str) -> str:
    if not cover_url:
        return ""

    name = cover_url.split('/')[-1].split('?')[0]
    stem = Path(name).stem
    folder = Path(jacket_path)
    for path in (folder / f"{stem}.webp", Path("otoge_cache/jackets") / f"{stem}.webp", folder / name,
                 folder / f"{stem}.jpg", folder / f"{stem}.png"):
        if not path.exists():
            continue
        try:
            jacket_data = base64.b64encode(path.read_bytes()).decode('utf-8')
        except Exception as e:
            print(f"Error loading jacket from {path}: {e}")
            continue
        content_type = {'.png': 'image/png', '.webp': 'image/webp'}.get(path.suffix.lower(), 'image/jpeg')
        return f'<img src="data:{content_type};base64,{jacket_data}" class="cover-img" />'
    return ""


def _cover_markup(rec: "Recommendation", jacket_path: str, css_class: str) -> str:
    cover_html = _load_local_jacket(rec.cover_url, jacket_path)
    if cover_html:
        return cover_html.replace('class="cover-img"', f'class="{css_class}"')
    return f'<div class="{css_class} no-cover"></div>'


def cover_html_factory(jacket_path: str):
    """Cover renderer for posters.py: (cover_url, css_class) -> <img> or placeholder.

    :param jacket_path: Where the cached jackets live.
    :type jacket_path: str
    """
    def render(cover_url: str, css_class: str) -> str:
        stub = Recommendation(
            song="", difficulty=0, current_accuracy=0, target_accuracy=0, current_rating=0, target_rating=0,
            potential_gain=0, max_possible_gain=0, current_rank="", target_rank="", fc_status="", is_new=False,
            priority_score=0, effort_score=0, efficiency=0,
            cover_url=cover_url.split("/")[-1].split("?")[0] if cover_url else "",
        )
        return _cover_markup(stub, jacket_path, css_class)
    return render


def generate_poster_html(recommendations: List[Recommendation], player_name: str, player_rating: int,
                         fc: int, fc_plus: int, clears: int, avatar_base64: str = "",
                         jacket_path: str = "otoge_cache/jackets/",
                         plan: Optional["analysis.Plan"] = None, image_gain: Optional[int] = None, scope: str = "",
                         summary: Optional[Dict[str, Any]] = None, counts: str = "") -> str:
    movers = [r for r in recommendations if r.category not in ("near", "try")]
    near = [r for r in recommendations if r.category == "near"][:8]
    # gains overlap once several picks land, so the headline is the simulated total when the caller has it
    total_gain = image_gain if image_gain is not None else sum(r.potential_gain for r in movers)
    featured, listed = movers[:3], movers[3:15]
    steps = plan.steps[:16] if plan else []
    cover = cover_html_factory(jacket_path)

    def stub(position: int, difficulty: str, constant: float, gain: int) -> str:
        return (f'<div class="track-stub"><b>{position}</b>{tier_mark(difficulty)}'
                f'{f"<small>{constant:.1f}</small>" if constant else ""}<strong>+{gain}</strong></div>')

    def name(title: str, unplayed: bool, chart_type: str) -> str:
        return f'<div class="track-name"><b>{_esc(title)}</b>{mark("new") if unplayed else ""}{kind_mark(chart_type)}</div>'

    def move(current_rank: str, target_rank: str) -> str:
        return f'{rank_mark(current_rank)}<i class="an-to">&rarr;</i>{rank_mark(target_rank)}' if current_rank else rank_mark(target_rank)

    def ticket(position: int, title: str, chart_type: str, difficulty: str, constant: float, unplayed: bool,
               current: float, target: float, current_rank: str, target_rank: str, gain: int, cover_url: str,
               place: str = "", post: str = "") -> str:
        _label, ink = tier(difficulty)
        return f"""
        <div class="track" style="--tier:{ink};{place}">
          {stub(position, difficulty, constant, gain)}
          <div class="track-body">
            {name(title, unplayed, chart_type)}
            {cover(cover_url, "track-jacket")}
            <div class="track-score"><b>{target:.2f}%</b><small>{"never played" if unplayed else f"from {current:.2f}%"}</small></div>
            <div class="track-foot"><span>{move(current_rank, target_rank)}</span></div>
          </div>{post}
        </div>"""

    picks = ""
    for position, rec in enumerate(featured, 1):
        label, ink = tier(rec.difficulty_type)
        now = "never played" if rec.is_unplayed else f"now {rec.current_accuracy:.2f}% {rank_mark(rec.current_rank)}"
        picks += f"""
        <div class="track an-big" style="--tier:{ink};">
          {stub(position, rec.difficulty_type, rec.difficulty, rec.potential_gain)}
          <div class="an-big-body">
            {name(rec.song, rec.is_unplayed, rec.chart_type)}
            {cover(rec.cover_url, "an-big-jacket")}
            <div class="an-big-move">
              <small>{label.title()} {_esc(rec.level)}, <em>{rec.feasibility * 100:.0f}% odds</em></small>
              <span class="an-big-now">{now}</span>
              <span class="an-big-goal"><i class="an-to">&rarr;</i>{rec.target_accuracy:.2f}%{rank_mark(rec.target_rank)}</span>
              <small>{_plays(rec.plays, rec.is_unplayed)}<br>you usually score {rec.expected:.1f}% here</small>
            </div>
          </div>
        </div>"""

    banner = [stats([("Rating", rating_plate(player_rating, small=True))]
                    + [(label, _esc(value)) for label, value in (("FC", fc), ("FC+", fc_plus), ("Clears", clears)) if value])]
    if summary:
        profile, best50 = summary.get("profile", {}), summary.get("best50", {})
        open_slots = best50.get("newSlotsOpen", 0) + best50.get("oldSlotsOpen", 0)
        banner.append(f'<div class="sum"><span>{_esc(best50.get("newTotal", 0))}<small>new</small></span><i>+</i>'
                      f'<span>{_esc(best50.get("oldTotal", 0))}<small>old</small></span><i>=</i>'
                      f'<span><b>{_esc(best50.get("total", 0))}</b><small>best 50</small></span></div>')
        banner.append(stats([
            ("Style", f"{_esc(str(profile.get('style', 'unknown')).title())}<small>leans {_esc(str(profile.get('favoriteChartType', '?')).upper())}</small>"),
            ("FC · AP · DX score", f"{profile.get('fcRate', 0) * 100:.0f}% / {profile.get('apRate', 0) * 100:.0f}% / {profile.get('dxScoreRate', 0) * 100:.0f}%"),
            ("SS up to", _esc(profile.get("comfortConstant", 0))),
            ("S up to", _esc(profile.get("reachConstant", 0))),
            ("Hardest S", _esc(profile.get("hardestS", 0))),
            ("Usual on 13 / 14", f"{_esc(profile.get('expectedAt13', 0))}% / {_esc(profile.get('expectedAt14', 0))}%"),
            ("Cutoffs", f"{_esc(best50.get('newCutoff', 0))}<small>new</small> / {_esc(best50.get('oldCutoff', 0))}<small>old</small>"),
        ] + ([("Slots empty", _esc(open_slots))] if open_slots else [])))
    if steps:
        road = [("Expected", f"+{plan.expected_gain:.0f}"), ("Over your usual", f"{plan.average_stretch:+.1f}%")]
        if plan.gap_steps:
            road.append(("Never played", f"{len(plan.gap_steps)}<small>worth +{plan.gap_gain}</small>"))
        elif not plan.reached:
            road.append(("Never played", "0<small>none would enter your best 50</small>"))
        banner.append(stats(road))

    # the picks stand beside the road only when they run about as long; a short list goes above a full-width road
    split = bool(listed and steps) and math.ceil(len(listed) / 3) >= math.ceil(len(steps) / 4)
    across, road_across, left = 8, 8, 0
    if split:
        # picks and road share one tile width (5:4) so their rows line up; take the most rows that fit under the head at 16:9; when not even
        # one row fits, the picks go above a full-width road, which fits a list that short. 2296px is the width less the gaps: 14px between picks, 52px per step for the road's lane, 10px at its
        # end. 521px is 1350 less the head, banner and footer, the picks row and the board's heading, goal and gap; a split always has
        # picks, and their row is as tall with the near list beside them as without it
        room = 521
        for rows in range(1, 7):
            a, b = math.ceil(len(listed) / rows), math.ceil(len(steps) / rows)
            tile = (2296 - 14 * (a - 1) - 52 * b - 10) / (a + b)
            if rows * (0.8 * tile + 16) > room:
                break
            across, road_across, left = a, b, round(a * tile + 14 * (a - 1))
        split = bool(left)
    road_rows = math.ceil(len(steps) / road_across) + 1 if steps else 0
    board = ""
    if listed:
        plates = "".join(
            ticket(position, rec.song, rec.chart_type, rec.difficulty_type, rec.difficulty, rec.is_unplayed,
                   rec.current_accuracy, rec.target_accuracy, rec.current_rank, rec.target_rank, rec.potential_gain, rec.cover_url)
            for position, rec in enumerate(listed, len(featured) + 1))
        board += panel("pink run an-next", "Next up", f'<div class="tracks" style="--across:{across}">{plates}</div>',
                       f"picks {len(featured) + 1} to {len(featured) + len(listed)}" if len(listed) > 1 else f"pick {len(featured) + 1}")
    if steps:
        # each row of the road runs left to right like a line of text, and the total so far stands on the road after every step
        lanes = "".join(f'<i class="an-lane" style="grid-row:{row + 1}"></i>' for row in range(road_rows - 1))
        plates = ""
        for index, step in enumerate(steps):
            row, column = divmod(index, road_across)
            option = step.option
            plates += ticket(index + 1, option.title, option.chart_type, option.difficulty_type, option.constant, option.is_unplayed,
                             option.current_accuracy, option.target_accuracy, option.current_rank, option.target_rank, step.gain, option.cover,
                             f"grid-area:{row + 1}/{column + 1}", f'<em class="an-post">+{step.cumulative}</em>')
        verdict = (f"covers the full +{plan.needed}" if plan.reached
                   else f"+{plan.total} of +{plan.needed}, {plan.shortfall} short")
        filled = min(100, 100 * plan.total / plan.needed) if plan.needed else 100
        plates += (f'<div class="track head an-goal" style="--tier:var(--gold);grid-row:{road_rows};grid-column:1 / -1">'
                   f'<div class="track-stub">{mark("dxstar")}</div><div class="track-body">'
                   f'<b>Goal</b><strong>{plan.goal_rating}</strong>'
                   f'<span class="an-meter"><i style="width:{filled:.0f}%"></i></span>'
                   f'<small>{_esc(verdict)}, from {plan.start_rating}. Play them in order. Each step shows your total after it.</small></div></div>')
        board += panel("cyan run an-road", f"Road to {plan.goal_rating}",
                       f'<div class="an-path" style="--across:{road_across}">{lanes}{plates}</div>',
                       f"{len(steps)} step{'' if len(steps) == 1 else 's'}")

    body = f'<div class="banner">{"".join(banner)}</div>'
    top = ""
    if picks:
        # our own wording for the scope ("level 13+"), never the player's text
        top = panel("gold run", "Play these first", f'<div class="tracks an-picks" style="--across:{len(featured)}">{picks}</div>',
                      f"top {len(featured)} of {len(movers)}" + (f" · {scope}" if scope else ""))
    outside = ""
    if near:
        items = "".join(
            f'<div class="track an-near" style="--tier:{tier(r.difficulty_type)[1]}"><div class="track-stub">{tier_mark(r.difficulty_type)}</div>'
            f'<div class="an-near-body"><b>{_esc(r.song)}</b><span>{"" if top else "reach "}<em>{r.required_accuracy:.2f}%</em></span></div></div>'
            for r in near)
        # beside the picks the near list sits two across in their height, leaving the rows below to the board
        outside = panel("purple run" + (" an-outside" if top else ""), "Just outside your best 50",
                        f'<div class="tracks" style="--across:{2 if top else len(near)}">{items}</div>',
                        "they count at the score shown" if top else "these pay nothing yet · reach the score shown and they start counting")
    body += f'<div class="an-top">{top}{outside}</div>' if top and outside else top
    if board:
        body += f'<div class="an-board{" an-split" if split else ""}" style="--left:{left}px">{board}</div>'
    if outside and not top:
        body += outside

    return _page("What to play next", player_name, avatar_base64, f"+{total_gain}", "possible gain",
                 f'<div class="an">{body}</div>',
                 counts, datetime.now().strftime("%d %B %Y"))


CHROMIUM_ARGS = [
    "--no-sandbox", "--disable-setuid-sandbox", "--disable-gpu", "--disable-dev-shm-usage",
    "--no-zygote", "--disable-features=dbus",
]


_browser_state: Dict[str, Any] = {"playwright": None, "browser": None}


_browser_lock: Optional[asyncio.Lock] = None


async def _launch(playwright):
    """Headless shell first; if it dies on this host (emulation, seccomp), the full browser in single-process mode.

    :param playwright: The running Playwright driver.
    """
    try:
        return await playwright.chromium.launch(headless=True, args=CHROMIUM_ARGS)
    except Exception as first:
        logger.warning(f"Headless shell failed to start ({type(first).__name__}); retrying with the full browser")
        return await playwright.chromium.launch(
            headless=True, channel="chromium", args=CHROMIUM_ARGS + ["--single-process"]
        )


async def _get_browser():
    """The shared browser, started on first use. Launch costs ~0.6s, so it is kept for the life of the process."""
    global _browser_lock
    if _browser_lock is None:
        _browser_lock = asyncio.Lock()
    async with _browser_lock:
        browser = _browser_state["browser"]
        if browser is not None and browser.is_connected():
            return browser
        await _drop_browser()
        playwright = await async_playwright().start()
        browser = await _launch(playwright)
        _browser_state["playwright"], _browser_state["browser"] = playwright, browser
        return browser


async def _drop_browser() -> None:
    browser, playwright = _browser_state["browser"], _browser_state["playwright"]
    _browser_state["browser"] = _browser_state["playwright"] = None
    for closer in ((browser.close if browser else None), (playwright.stop if playwright else None)):
        if closer:
            try:
                await closer()
            except Exception:
                pass


# The classic recent board flows its plays down CSS columns, which Blitz has no layout for, so Chromium draws it
BLITZ_UNSUPPORTED = ('class="recent-flow"',)
BLITZ_TIMEOUT = 30          # seconds for one page; the largest poster takes about 0.3

# blitz (blitz/) is one long-lived process: started on first use, it keeps its fonts loaded between pages.
# The process and the lock that keeps one page in its pipe at a time belong to the event loop that started them; a new
# loop starts both afresh
_blitz: Dict[str, Any] = {"path": None, "looked": False, "loop": None, "lock": None, "proc": None}


def _blitz_path() -> Optional[str]:
    """Where the blitz binary is, or None when the images are drawn with Chromium."""
    if not _blitz["looked"]:
        _blitz["looked"] = True
        _blitz["path"] = None if RENDERER.lower() in ("", "chromium") else RENDERER
    return _blitz["path"]


def _stop_blitz() -> None:
    proc, _blitz["proc"] = _blitz["proc"], None
    if proc is not None and proc.returncode is None:
        try:
            proc.kill()
        except Exception:
            pass


async def _render_with_blitz(path: str, html_content: str) -> bytes:
    """The page drawn by blitz: its byte count and HTML in on stdin, a byte count and the PNG back on stdout.

    :param path: Where the blitz binary is.
    :type path: str
    :param html_content: The page.
    :type html_content: str
    :rtype: bytes
    """
    loop = asyncio.get_running_loop()
    if _blitz["loop"] is not loop:
        _stop_blitz()
        _blitz.update(loop=loop, lock=asyncio.Lock())
    async with _blitz["lock"]:
        proc = _blitz["proc"]
        if proc is None or proc.returncode is not None:
            try:
                proc = _blitz["proc"] = await asyncio.create_subprocess_exec(
                    path, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE)
            except OSError:
                _blitz["path"] = None       # not there or not runnable: say so once, and draw with Chromium from now on
                raise
        data = html_content.encode("utf-8")
        try:
            proc.stdin.write(len(data).to_bytes(4, "little") + data)
            await proc.stdin.drain()
            size = int.from_bytes(await asyncio.wait_for(proc.stdout.readexactly(4), BLITZ_TIMEOUT), "little")
            png = await asyncio.wait_for(proc.stdout.readexactly(size), BLITZ_TIMEOUT)
        except BaseException:
            _stop_blitz()       # stopped mid-page, its pipe is out of step with the next one
            raise
    if not png:
        raise RuntimeError("blitz could not draw the page (its reason is in the log)")
    return png


async def render_html_to_image(html_content: str) -> bytes:
    """The page as a PNG, drawn by Blitz, or by Chromium where it is not installed, cannot lay the
    page out, or fails on it.

    :param html_content: The page.
    :type html_content: str
    :rtype: bytes
    """
    path = _blitz_path()
    if path and not any(marker in html_content for marker in BLITZ_UNSUPPORTED):
        try:
            return await _render_with_blitz(path, html_content)
        except Exception as error:
            logger.warning(f"Blitz could not draw the page ({type(error).__name__}: {error}); drawing it with Chromium")
    return await _render_with_chromium(html_content)


async def _render_with_chromium(html_content: str) -> bytes:
    browser = await _get_browser()
    context = None
    try:
        context = await browser.new_context(viewport={"width": 2400, "height": 400}, device_scale_factor=1)
        page = await context.new_page()
        # everything the page shows is inside it, so it is ready once loaded and its fonts are in; waiting for the network to
        # stay idle and then a fixed pause added most of a second to every image
        await page.set_content(html_content, wait_until="load")
        await page.evaluate("document.fonts.ready.then(() => 0)")
        # the body sets its own width (2400 for posters, narrower for cards), so clip to it, not the viewport
        dimensions = await page.evaluate(
            "() => ({ width: document.body.offsetWidth || Math.max(document.body.scrollWidth, document.documentElement.scrollWidth),"
            " height: Math.max(document.body.scrollHeight, document.documentElement.scrollHeight) })"
        )
        return await page.screenshot(
            full_page=True,
            clip={"x": 0, "y": 0, "width": dimensions["width"], "height": dimensions["height"]},
        )
    except Exception:
        # A dead renderer would poison every later call; forget it so the next render relaunches.
        # A failure on one page while others are mid-render is not that.
        if not browser.is_connected():
            await _drop_browser()
        raise
    finally:
        if context is not None:
            try:
                await context.close()
            except Exception:
                pass
