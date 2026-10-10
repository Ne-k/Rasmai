import os
import asyncio
import io
import logging
import signal
import sys
import threading
import traceback

from rasmai.bot.core import bot
from rasmai.config import get_public_base_url, public_url_is_shareable
from rasmai.web.tunnel import start_tunnel_if_configured, stop_tunnel
from rasmai.web.web_server import InternalApiServer

logger = logging.getLogger(__name__)


def dump_stacks(signum=None, frame=None) -> None:
    """Log where every thread and every pending asyncio task is right now.

    A command stuck on "thinking" logs nothing on its own, so this is how to see what it waits on:
    ``docker kill -s USR1 rasmai`` and then ``docker logs rasmai``.
    """
    try:
        names = {t.ident: t.name for t in threading.enumerate()}
        parts = []
        for ident, top in sys._current_frames().items():
            parts.append(f"--- thread {names.get(ident, ident)}\n{''.join(traceback.format_stack(top))}")
        try:
            loop = asyncio.get_running_loop()       # the handler runs in the main thread, where bot.run keeps its loop
        except RuntimeError:
            loop = None
        if loop is not None:
            for task in asyncio.all_tasks(loop):
                out = io.StringIO()
                task.print_stack(file=out)
                parts.append(f"--- task {task.get_name()}\n{out.getvalue()}")
        logger.warning("Stack dump on request:\n%s", "\n".join(parts))
    except Exception:
        # a diagnostic must never take the bot down with it
        logger.exception("Stack dump failed")


def main():
    TOKEN = os.getenv('DISCORD_TOKEN')

    if not TOKEN:
        print("DISCORD_TOKEN not found in environment variables!")
        print("Please create a .env file with DISCORD_TOKEN=your_bot_token")
        return

    if hasattr(signal, "SIGUSR1"):      # Windows has no SIGUSR1
        signal.signal(signal.SIGUSR1, dump_stacks)

    from rasmai.errors import install as report_errors
    report_errors()

    web_server = InternalApiServer()
    web_server.start()
    start_tunnel_if_configured()

    if public_url_is_shareable():
        logger.info(f"Connect site is public at {get_public_base_url()}")
    else:
        logger.warning(
            f"Connect site is only reachable at {get_public_base_url()}. Other people cannot use /login "
            "until it has an https address: set MAIMAI_PUBLIC_URL, or MAIMAI_TUNNEL=quick with cloudflared installed."
        )

    try:
        bot.run(TOKEN)
    finally:
        stop_tunnel()
        web_server.stop()


if __name__ == "__main__":
    main()
