from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Callable, List, Optional, Tuple
import asyncio
import logging

import discord
import requests

from rasmai.bot.ui.formatting import stamp
from rasmai.config import BROWSER_USER_AGENT, PRESENCE_ENABLED, PRESENCE_REGION, get_maimai_base_url

logger = logging.getLogger(__name__)

JST = timezone(timedelta(hours=9))

# Published maintenance for the international version, from 1 September 2026:
# every day 01:00-02:00 JST, and 01:00-04:00 JST on Wednesdays.
DAILY_WINDOW = (time(1, 0), time(2, 0))
WEDNESDAY_WINDOW = (time(1, 0), time(4, 0))
WEDNESDAY = 2

WARN_AHEAD = timedelta(minutes=30)
PROBE_TIMEOUT = 8
PROBE_EVERY = timedelta(minutes=10)
PROBE_EVERY_NEAR_WINDOW = timedelta(minutes=3)
PROBE_EVERY_WHEN_DOWN = timedelta(minutes=1)   # once it stops answering, look again every tick so a recovery shows up at once
PROBE_MISSES = 2                               # failed probes in a row before the site is called down


@dataclass
class Maintenance:
    active: bool
    moment: datetime          # when it ends if active, when the next one starts if not

    @property
    def minutes_away(self) -> int:
        return max(0, int((self.moment - datetime.now(JST)).total_seconds() // 60))

    @property
    def imminent(self) -> bool:
        return not self.active and self.moment - datetime.now(JST) <= WARN_AHEAD


def window_on(day: date) -> Tuple[datetime, datetime]:
    """The maintenance window for one JST day.

    :param day: The day to group under.
    :type day: date
    :rtype: Tuple[datetime, datetime]
    """
    opens, closes = WEDNESDAY_WINDOW if day.weekday() == WEDNESDAY else DAILY_WINDOW
    return datetime.combine(day, opens, JST), datetime.combine(day, closes, JST)


def maintenance_at(now: Optional[datetime] = None) -> Maintenance:
    """Whether the servers are down on the published schedule, and until (or from) when.

    :param now: The moment to measure from.
    :type now: Optional[datetime]
    :rtype: Maintenance
    """
    now = now or datetime.now(JST)
    now = now.astimezone(JST)
    opens, closes = window_on(now.date())
    if opens <= now < closes:
        return Maintenance(True, closes)
    if now < opens:
        return Maintenance(False, opens)
    return Maintenance(False, window_on(now.date() + timedelta(days=1))[0])


def _probe_once(region: str) -> bool:
    """Whether maimai DX NET answers at all. Any HTTP reply counts: signed out is still up.

    :param region: ``"intl"``, ``"jp"`` or ``"cn"``.
    :type region: str
    :rtype: bool
    """
    try:
        response = requests.get(
            f"{get_maimai_base_url(region)}/maimai-mobile/",
            headers={"User-Agent": BROWSER_USER_AGENT},
            allow_redirects=False, timeout=PROBE_TIMEOUT,
        )
        return response.status_code < 500
    except requests.RequestException as error:
        logger.info(f"maimai DX NET did not answer: {type(error).__name__}")
        return False


class ServerWatch:
    """Keeps the bot's presence in step with maimai's maintenance schedule."""

    def __init__(self, bot: discord.Client, region: str = PRESENCE_REGION):
        self.bot = bot
        self.region = region
        self.reachable = True
        self._misses = 0
        self.checked_at: Optional[datetime] = None
        self._task: Optional[asyncio.Task] = None
        self._shown: Optional[Tuple[str, str]] = None
        self._was_up: Optional[bool] = None
        self.on_up: List[Callable[[], None]] = []    # called once each time the servers come back

    def state(self) -> Tuple[discord.Status, str]:
        """The presence to show right now.

        :rtype: Tuple[discord.Status, str]
        """
        window = maintenance_at()
        if window.active:
            return discord.Status.dnd, f"maimai maintenance · back in {window.minutes_away}m"
        if not self.reachable:
            return discord.Status.dnd, "maimai DX NET is not answering"
        if window.imminent:
            return discord.Status.idle, f"maimai maintenance in {window.minutes_away}m"
        return discord.Status.online, "maimai DX · /analyze to see what to play"

    async def _refresh_probe(self) -> None:
        """Ask maimai DX NET whether it answers, no more often than the state of things warrants.

        A single failed probe is a blip, so it takes two in a row to call the site down; once it is
        down the next look comes a minute later rather than ten, so the minutes after a window closes
        do not report an outage that is already over."""
        window = maintenance_at()
        if window.active or window.imminent:
            due = PROBE_EVERY_NEAR_WINDOW
        elif not self.reachable or self._misses:
            due = PROBE_EVERY_WHEN_DOWN
        else:
            due = PROBE_EVERY
        if self.checked_at and datetime.now(JST) - self.checked_at < due:
            return
        answered = await asyncio.to_thread(_probe_once, self.region)
        self.checked_at = datetime.now(JST)
        if answered:
            if not self.reachable:
                logger.info("maimai DX NET is answering again")
            self._misses = 0
            self.reachable = True
            return
        self._misses += 1
        self.reachable = self._misses < PROBE_MISSES

    async def tick(self) -> None:
        await self._refresh_probe()
        up = self.reachable and not maintenance_at().active
        if up and self._was_up is False:
            for callback in self.on_up:
                try:
                    callback()
                except Exception:
                    logger.exception("on_up callback failed")
        self._was_up = up
        status, message = self.state()
        if self._shown == (status.value, message):
            return
        await self.bot.change_presence(status=status, activity=discord.CustomActivity(name=message[:128]))
        self._shown = (status.value, message)
        logger.info(f"Presence: {status.value} · {message}")

    async def _run(self) -> None:
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            try:
                await self.tick()
            except Exception:
                logger.exception("Presence update failed")
            await asyncio.sleep(60)

    def start(self) -> None:
        if not PRESENCE_ENABLED:
            logger.info("Presence updates are off (MAIMAI_PRESENCE=false)")
            return
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run())


def describe() -> str:
    """One line about the servers, for /ping.

    The window is anchored to JST, which has no daylight saving; Discord renders
    the timestamp in each reader's own zone, so their summer time is handled too.

    :rtype: str
    """
    window = maintenance_at()
    if window.active:
        return f"**In maintenance** · back {stamp(window.moment, 'R')} ({stamp(window.moment, 't')})"
    return f"**Up** · next maintenance {stamp(window.moment, 'R')} ({stamp(window.moment, 'f')})"
