from typing import Callable, Dict, List, Optional, Tuple
import asyncio
import logging
import time

import discord

from rasmai.config import PROGRESS_EDITS_PER_SECOND

logger = logging.getLogger(__name__)

# (key, label, typical seconds) - the estimate learns from real runs as the process lives
STEPS: List[Tuple[str, str, float]] = [
    ("login", "Signing in to maimai DX NET", 2.0),
    ("scores", "Reading score pages", 7.0),
    ("recent", "Recent plays", 1.0),
    ("extras", "Albums and events", 1.5),
    ("plays", "Play counts", 0.0),
    ("analysis", "Working out what to play", 1.0),
    ("render", "Drawing the image", 1.5),
]
PER_PLAY_COUNT = 1.0      # seconds per chart detail page, measured
EXPECTED_PLAY_COUNTS = 60  # assumed until the real number is known, so the estimate does not jump
EDIT_EVERY = 1.1          # Discord tolerates about five edits per five seconds on one message
BAR_WIDTH = 16

_learned: Dict[str, float] = {}


class Progress:
    """A loading bar with the current stage and a time estimate, edited into the deferred reply as work happens.

    The scraper runs in a thread; `from_thread` hands it a callback that is safe to
    call from there. Edits are throttled so a burst of updates becomes one edit, and
    every live bar shares one edit budget so a crowd of them stays inside Discord's
    global limit."""

    _active: set = set()

    def __init__(self, interaction: discord.Interaction, title: str = "Reading your scores from maimai"):
        self.interaction = interaction
        self.title = title
        self.status: Dict[str, str] = {key: "pending" for key, _l, _s in STEPS}
        self.done: Dict[str, int] = {key: 0 for key, _l, _s in STEPS}
        self.total: Dict[str, int] = {key: 0 for key, _l, _s in STEPS}
        self.note: Dict[str, str] = {}
        self.started: Dict[str, float] = {}
        self.began = time.monotonic()
        self._last_edit = 0.0
        self._dirty = False
        self._flusher: Optional[asyncio.Task] = None
        self._closed = False
        Progress._active.add(id(self))

    # ---- state
    def report(self, key: str, done: int = 0, total: int = 0, detail: str = "") -> None:
        if key not in self.status or self._closed:
            return
        if self.status[key] == "pending":
            self.status[key] = "active"
            self.started[key] = time.monotonic()
            for earlier, _l, _s in STEPS:
                if earlier == key:
                    break
                if self.status[earlier] == "active":
                    self.finish(earlier)
        self.done[key], self.total[key] = done, total
        if detail:
            self.note[key] = detail
        if total and done >= total:
            self.finish(key)
        self._dirty = True
        self._schedule()

    def finish(self, key: str) -> None:
        if self.status.get(key) == "done":
            return
        self.status[key] = "done"
        if key in self.started:
            taken = time.monotonic() - self.started[key]
            if key == "plays":
                taken = taken / max(1, self.total[key])
            # learn from real runs, but never let one odd measurement collapse or explode a weight
            default = PER_PLAY_COUNT if key == "plays" else next(s for k, _l, s in STEPS if k == key)
            taken = max(0.3 * default, min(5.0 * default, taken))
            _learned[key] = taken if key not in _learned else 0.7 * _learned[key] + 0.3 * taken

    def only(self, *keys: str) -> "Progress":
        """Show just these steps; the others are skipped and weigh nothing.

        :rtype: 'Progress'
        """
        for key, _l, _s in STEPS:
            if key not in keys:
                self.status[key] = "skipped"
        return self

    def skip(self, key: str, why: str = "") -> None:
        self.status[key] = "skipped"
        if why:
            self.note[key] = why
        self._dirty = True
        self._schedule()

    def from_thread(self) -> Callable[..., None]:
        loop = asyncio.get_running_loop()

        def callback(key: str, done: int = 0, total: int = 0, detail: str = "") -> None:
            loop.call_soon_threadsafe(self.report, key, done, total, detail)
        return callback

    # ---- estimate
    def _nominal(self, key: str) -> float:
        if self.status[key] == "skipped":
            return 0.0
        if key == "plays":
            return _learned.get("plays", PER_PLAY_COUNT) * (self.total["plays"] or EXPECTED_PLAY_COUNTS)
        return _learned.get(key, next(s for k, _l, s in STEPS if k == key))

    def fraction_and_remaining(self) -> Tuple[float, float]:
        total_weight = sum(self._nominal(k) for k, _l, _s in STEPS) or 1.0
        earned = 0.0
        remaining = 0.0
        for key, _label, _seconds in STEPS:
            weight = self._nominal(key)
            if self.status[key] in ("done", "skipped"):
                earned += weight
            elif self.status[key] == "active":
                part = (self.done[key] / self.total[key]) if self.total[key] else 0.0
                spent = time.monotonic() - self.started.get(key, time.monotonic())
                part = max(part, min(0.9, spent / weight) if weight else 0.0)
                earned += weight * part
                remaining += weight * (1 - part)
            else:
                remaining += weight
        return min(1.0, earned / total_weight), remaining

    # ---- text
    def render(self) -> str:
        fraction, remaining = self.fraction_and_remaining()
        eta = "almost there" if remaining < 3 else f"about {int(round(remaining / 5.0) * 5) or 5}s left"
        current = ""
        for key, label, _seconds in STEPS:
            if self.status[key] == "active":
                current = self.note.get(key) or label
                if self.total[key] > 1:
                    current += f" {self.done[key]}/{self.total[key]}"
                break
        filled = max(0, min(BAR_WIDTH, round(BAR_WIDTH * fraction)))
        bar = "▰" * filled + "▱" * (BAR_WIDTH - filled)
        tail = f" · {current}" if current else ""
        return f"**{self.title}**\n`{bar}` {int(fraction * 100)}%{tail} · {eta}"

    # ---- edits
    def _schedule(self) -> None:
        if self._closed or (self._flusher and not self._flusher.done()):
            return
        self._flusher = asyncio.create_task(self._flush_when_allowed())

    def _interval(self) -> float:
        return max(EDIT_EVERY, len(Progress._active) / PROGRESS_EDITS_PER_SECOND)

    async def _flush_when_allowed(self) -> None:
        wait = self._interval() - (time.monotonic() - self._last_edit)
        if wait > 0:
            await asyncio.sleep(wait)
        await self.flush()

    async def flush(self, force: bool = False) -> None:
        if self._closed or not (self._dirty or force):
            return
        self._dirty = False
        self._last_edit = time.monotonic()
        try:
            await self.interaction.edit_original_response(content=self.render(), embed=None, attachments=[], view=None)
        except discord.HTTPException as error:
            logger.debug(f"progress edit skipped: {error}")

    def close(self) -> None:
        """Stop editing: the real reply is about to replace this text."""
        self._closed = True
        Progress._active.discard(id(self))
        if self._flusher and not self._flusher.done():
            self._flusher.cancel()
