import os
import logging

from rasmai.bot.core import bot
from rasmai.config import get_public_base_url, public_url_is_shareable
from rasmai.web.tunnel import start_tunnel_if_configured, stop_tunnel
from rasmai.web.web_server import InternalApiServer

logger = logging.getLogger(__name__)


def main():
    TOKEN = os.getenv('DISCORD_TOKEN')

    if not TOKEN:
        print("DISCORD_TOKEN not found in environment variables!")
        print("Please create a .env file with DISCORD_TOKEN=your_bot_token")
        return

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
