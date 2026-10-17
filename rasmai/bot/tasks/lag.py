from typing import Optional
import asyncio
import logging
import os
import sys
import threading
import time
import traceback

logger = logging.getLogger(__name__)

THRESHOLD = 2.0         # seconds the loop may go without running before it is said so: Discord wants an answer inside three
BEAT = 0.25             # seconds between the loop's own signs of life


class LagWatch:
    """Says what the bot was doing whenever its event loop stops answering for a couple of seconds.

    Discord drops a command it is not answered inside three seconds, and a stall that long leaves nothing in the log
    but "answered too late". A thread outside the loop watches the loop's heartbeat, and when it goes quiet it records where
    the loop's own thread is, which is the blocking call if there is one, and what every other thread is doing, which is the
    cause when the loop is merely starved by them.
    """

    def __init__(self, threshold: float = THRESHOLD):
        self.threshold = threshold
        self.beat = time.monotonic()
        self._ident = 0
        self._thread: Optional[threading.Thread] = None
        self._pulse_task: Optional[asyncio.Task] = None
        self._stopped = threading.Event()

    def start(self) -> None:
        """Begin watching the running loop. Once, however many times Discord reconnects."""
        if self._thread is not None:
            return
        self._ident = threading.get_ident()
        self.beat = time.monotonic()
        self._pulse_task = asyncio.get_running_loop().create_task(self._pulse())
        self._thread = threading.Thread(target=self._watch, name="lag-watch", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop watching, for a loop that is being closed: its silence afterwards is not a stall."""
        self._stopped.set()
        if self._pulse_task is not None:
            self._pulse_task.cancel()

    async def _pulse(self) -> None:
        while True:
            self.beat = time.monotonic()
            await asyncio.sleep(BEAT)

    def _where(self) -> str:
        frames = sys._current_frames()
        loop_frame = frames.get(self._ident)
        loop_at = "".join(traceback.format_stack(loop_frame)[-3:]).rstrip() if loop_frame is not None else "(unknown)"
        others = []
        for thread in threading.enumerate():
            frame = frames.get(thread.ident or 0)
            if frame is None or thread.ident in (self._ident, threading.get_ident()):
                continue
            others.append(f"{thread.name}: {os.path.basename(frame.f_code.co_filename)}:{frame.f_lineno} {frame.f_code.co_name}")
        return f"the loop's thread is in:\n{loop_at}\nthe other threads are in: {'; '.join(others) or 'none'}"

    def _watch(self) -> None:
        began: Optional[float] = None
        while not self._stopped.wait(self.threshold / 4):
            late = time.monotonic() - self.beat
            if began is None and late >= self.threshold:
                began = self.beat
                logger.warning("the event loop has not run for %.1fs; %s", late, self._where())
            elif began is not None and late < self.threshold:
                logger.warning("the event loop ran again after %.1fs", time.monotonic() - began)
                began = None
