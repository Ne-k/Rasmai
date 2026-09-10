from typing import Optional
import re
import shutil
import subprocess
import threading
import logging

from rasmai.config import (
    PUBLIC_URL,
    TUNNEL_MODE,
    TUNNEL_ORIGIN,
    get_public_base_url,
    set_public_base_url,
)

logger = logging.getLogger(__name__)


_tunnel_process: Optional[subprocess.Popen] = None


_TUNNEL_URL = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")


def _pump_tunnel_output(process: subprocess.Popen, on_url) -> None:
    for line in process.stdout:
        match = _TUNNEL_URL.search(line)
        if match and on_url is not None:
            on_url(match.group(0))
            on_url = None
        logger.debug(f"cloudflared: {line.rstrip()}")


def start_tunnel_if_configured() -> Optional[str]:
    """Run cloudflared alongside the bot.

    :rtype: Optional[str]
    """
    global _tunnel_process
    if not TUNNEL_MODE:
        return None
    executable = shutil.which("cloudflared")
    if not executable:
        logger.error("MAIMAI_TUNNEL is set but cloudflared is not on PATH. Install it from "
                     "https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/installation/")
        return None

    quick = TUNNEL_MODE.lower() == "quick"
    # the tunnel fronts the website (the Next.js server), not the bot's internal API
    if quick:
        command = [executable, "tunnel", "--no-autoupdate", "--url", TUNNEL_ORIGIN]
    else:
        if not PUBLIC_URL:
            logger.error(f"MAIMAI_TUNNEL={TUNNEL_MODE} needs MAIMAI_PUBLIC_URL set to the hostname routed to that tunnel")
            return None
        command = [executable, "tunnel", "--no-autoupdate", "run", TUNNEL_MODE]

    _tunnel_process = subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace",
    )
    found = threading.Event()

    def adopt(url: str) -> None:
        set_public_base_url(url)
        found.set()

    threading.Thread(
        target=_pump_tunnel_output, args=(_tunnel_process, adopt if quick else None), daemon=True
    ).start()
    if quick and not found.wait(45):
        logger.error("cloudflared started but never printed a trycloudflare.com URL; /login links will be local-only")
    return get_public_base_url()


def stop_tunnel() -> None:
    if _tunnel_process and _tunnel_process.poll() is None:
        _tunnel_process.terminate()
