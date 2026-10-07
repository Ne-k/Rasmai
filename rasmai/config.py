from datetime import timedelta
from pathlib import Path
import logging
import os
import re
import threading


def load_env(path):
    # a variable that is already set keeps its value, as it does with python-dotenv
    try:
        text = Path(path).read_text(encoding="utf-8-sig")
    except OSError:
        return
    for line in text.splitlines():
        key, sep, value = line.strip().removeprefix("export ").partition("=")
        key, value = key.strip(), value.strip()
        if not sep or not key or key.startswith("#"):
            continue
        if len(value) > 1 and value[0] in "\"'" and value[-1] == value[0]:
            value = value[1:-1]
        else:
            value = re.sub(r"\s+#.*", "", value)
        os.environ.setdefault(key, value)


load_env(Path(__file__).resolve().parent.parent / ".env")


# MAIMAI_DEBUG turns on the verbose logs: what used to print only with a debug flag passed down by hand is logged at debug
logging.basicConfig(level=logging.DEBUG if os.getenv("MAIMAI_DEBUG", "false").lower() == "true" else logging.INFO)


DEBUG_EXPORT_JSON = os.getenv("MAIMAI_DEBUG_EXPORT_JSON", "false").lower() == "true"


DEBUG_EXPORT_DIR = Path("debug/maimai-exports")


# The bot's internal API, for the Next.js site in web/ to call. Not for browsers: keep it on
# loopback or the container network, and give both processes the same RASMAI_INTERNAL_SECRET.
WEBSERVER_HOST = os.getenv("MAIMAI_WEBSERVER_HOST", "127.0.0.1")
INTERNAL_API_SECRET = os.getenv("RASMAI_INTERNAL_SECRET", "").strip()

# the only Discord account the developer page answers to; everyone else gets a 404 from it. Empty
# means nobody: the developer page and /notice stay off until this is set
ADMIN_USER_ID = os.getenv("MAIMAI_ADMIN_ID", "").strip()

# where /notice is registered. A guild command exists only in that one server, so the rest of
# Discord never sees it in the picker; the admin check is what actually stops anyone using it.
CONTROL_GUILD_ID = int(os.getenv("MAIMAI_CONTROL_GUILD_ID", "0") or 0)

# the band the site shows until one is set from Discord; taking that one down leaves the site bare
DEFAULT_NOTICE = {
    "text": "Rasmai is moving to rasmai.lol. Your account and scores come with it, so you don't need to "
            "re-link. This address works until the move.",
    "tone": "notice",
    "link": "",
    "id": "move-rasmai-lol",
    "hideOnHost": "rasmai.lol",
}

# the linking walkthrough recordings: "walkthrough" in the container, web/public in a checkout
WALKTHROUGH_DIR = next((p for p in (Path("walkthrough"), Path("web/public/walkthrough")) if p.is_dir()), Path("walkthrough"))
# where a bot-run cloudflared tunnel should point: the public site, which is the Next.js server
TUNNEL_ORIGIN = os.getenv("MAIMAI_TUNNEL_ORIGIN", "http://127.0.0.1:3000").strip().rstrip("/")


WEBSERVER_PORT = int(os.getenv("MAIMAI_WEBSERVER_PORT", "8765"))


PUBLIC_URL = os.getenv("MAIMAI_PUBLIC_URL", "https://rasmai.lol").strip().rstrip("/")


TUNNEL_MODE = os.getenv("MAIMAI_TUNNEL", "").strip()   # "quick", or the name of a cloudflared tunnel


_public_base_url = PUBLIC_URL


_public_url_lock = threading.Lock()


DATABASE_PATH = Path(os.getenv("MAIMAI_DATABASE_PATH", "data/maimai.sqlite3"))


# an account whose maimai sign-in has been refused this many days, and not linked again since, is deleted
# the way /delete-account deletes it; 0 keeps such accounts until someone deletes them by hand
EXPIRED_ACCOUNT_DAYS = max(0, int(os.getenv("MAIMAI_EXPIRED_ACCOUNT_DAYS", "30") or 0))

# how many days before that deletion its owner is sent a DM saying so, when Discord lets the bot; 0 sends none
EXPIRED_ACCOUNT_WARN_DAYS = max(0, int(os.getenv("MAIMAI_EXPIRED_ACCOUNT_WARN_DAYS", "2") or 0))


MAIMAI_BASE_URLS = {
    "jp": "https://maimaidx.jp",
    "intl": "https://maimaidx-eng.com",
    "cn": "https://maimai.wahlap.com",
}

# The regions an account can actually be linked from. International signs in through SEGA's Aime
# gateway, whose session cookie the bookmarklet hands over and the bot replays. Japan has no session a
# server can replay, so a Japan account is linked with its SEGA ID and password, which the bot keeps
# encrypted and signs in to maimaidx.jp with on every read. China's site only opens inside WeChat and
# has no sign-in here yet; it is kept in the tables above so its pages have somewhere to point.
SUPPORTED_REGIONS = ("intl", "jp")

REGION_NAMES = {"intl": "International", "jp": "Japan", "cn": "China"}

# how each unsupported region signs in, for saying why its account cannot be linked
REGION_SIGN_IN = {
    "cn": "China accounts sign in with WeChat on Wahlap's site, which only opens inside WeChat",
}


def region_supported(region: str) -> bool:
    """Whether an account from this region can be linked.

    :param region: ``"intl"``, ``"jp"`` or ``"cn"``.
    :type region: str
    :rtype: bool
    """
    return region in SUPPORTED_REGIONS


def unsupported_region_text(region: str) -> str:
    """Why an account from this region cannot be linked, in a sentence or two for the player.

    :param region: ``"cn"``, or any other region with no sign-in.
    :type region: str
    :rtype: str
    """
    name = REGION_NAMES.get(region, region)
    how = REGION_SIGN_IN.get(region, f"{name} accounts sign in somewhere else")
    return (f"{name}-region accounts can't be linked yet. {how}, and Rasmai has no way to sign in there yet, "
            f"so the login could never finish, however many times you tried. International and Japan accounts "
            f"can be linked.")


# maimai DX NET's daily maintenance, in JST, as (opens, closes) hours: the international site is down
# 01:00-02:00 (01:00-04:00 on Wednesdays), Japan's and China's 04:00-07:00 every day
MAINTENANCE_HOURS = {
    "intl": {"daily": (1, 2), "wednesday": (1, 4)},
    "jp": {"daily": (4, 7), "wednesday": (4, 7)},
    "cn": {"daily": (4, 7), "wednesday": (4, 7)},
}


def get_maimai_base_url(region: str) -> str:
    return MAIMAI_BASE_URLS.get(region, MAIMAI_BASE_URLS["intl"])


def get_public_base_url() -> str:
    with _public_url_lock:
        return _public_base_url or f"http://{WEBSERVER_HOST}:{WEBSERVER_PORT}"


def set_public_base_url(url: str) -> None:
    global _public_base_url
    with _public_url_lock:
        _public_base_url = url.strip().rstrip("/")


def public_url_is_shareable() -> bool:
    """True when the login script can be loaded from an https origin.

    :rtype: bool
    """
    return get_public_base_url().startswith("https://")


# ---- capacity. Scraping is thread-per-analysis on top of asyncio; these bound the process, not a server.
MAX_CONCURRENT_SCRAPES = int(os.getenv("MAIMAI_MAX_CONCURRENT", "24"))     # full score reads running at once
MAX_CONCURRENT_RENDERS = int(os.getenv("MAIMAI_MAX_RENDERS", "4"))          # Chromium pages open at once
SCRAPE_WORKERS = MAX_CONCURRENT_SCRAPES + 16     # thread pool behind every blocking call
REQUESTS_PER_SECOND = float(os.getenv("MAIMAI_REQUESTS_PER_SECOND", "25"))  # to maimai DX NET from this process, all users together
PROGRESS_EDITS_PER_SECOND = float(os.getenv("MAIMAI_PROGRESS_EDITS_PER_SECOND", "8"))   # loading-bar edits, all users together
ANALYSIS_CACHE_MAX = int(os.getenv("MAIMAI_ANALYSIS_CACHE_MAX", "500"))     # finished analyses kept in memory
# analyses built for the dashboard at once. It is CPU work under one interpreter lock, so more at
# once is slower, not faster: a load test measured 2.9 a second one at a time and 1.5 a second eight at a time.
ANALYSIS_BUILDS = max(1, int(os.getenv("MAIMAI_ANALYSIS_BUILDS", "2")))
# how long a dashboard request waits on its own build before it is told to ask again; with a queue
# ahead of it, it does not wait at all
ANALYSIS_WAIT = float(os.getenv("MAIMAI_ANALYSIS_WAIT", "20"))
SHARD_COUNT = int(os.getenv("DISCORD_SHARD_COUNT", "0") or 0)              # 0 lets Discord pick


# the link that adds the bot to a server; /invite in Discord and /invite on the site both hand it out
DISCORD_BOT_INVITE = os.getenv("DISCORD_BOT_INVITE", "").strip()
# the support server; /support in Discord and /support on the site both hand it out
SUPPORT_INVITE = os.getenv("DISCORD_SUPPORT_INVITE", "").strip() or "https://discord.gg/EhfdWeK8Aq"


def support_line() -> str:
    """The line that sends someone with a problem to the support server, for the end of an error message.

    :rtype: str
    """
    return f"-# Still stuck? Ask in the support server: {SUPPORT_INVITE}"


def site_label() -> str:
    """The public address without its scheme, for footers and captions.

    :rtype: str
    """
    return get_public_base_url().split("://", 1)[-1].rstrip("/")


PLAY_COUNT_TTL = timedelta(hours=12)
# a stored read is reused while a light check says nothing changed; after this long it is read in full regardless,
# so chart constants and the profile never drift for more than a week
SNAPSHOT_MAX_AGE = timedelta(hours=int(os.getenv("MAIMAI_SNAPSHOT_MAX_AGE_HOURS", "168")))
# a command run this long after the last check of maimai DX NET checks again before answering from memory
RECHECK_AFTER = timedelta(minutes=int(os.getenv("MAIMAI_RECHECK_MINUTES", "3")))


PLAY_COUNT_FETCH_LIMIT = int(os.getenv("MAIMAI_PLAY_COUNT_FETCH_LIMIT", "60"))
WIKI_VIDEOS = os.getenv("MAIMAI_WIKI_VIDEOS", "true").lower() == "true"     # /chart links the chart's video from SilentBlue RemyWiki


# /news translates Japanese posts with a model on an Ollama server, such as the one on the machine the bot runs on; empty uses Google Translate only
TRANSLATE_URL = os.getenv("MAIMAI_TRANSLATE_URL", "").strip().rstrip("/")
TRANSLATE_MODEL = os.getenv("MAIMAI_TRANSLATE_MODEL", "translategemma:12b").strip()
TRANSLATE_KEEP_ALIVE = os.getenv("MAIMAI_TRANSLATE_KEEP_ALIVE", "2m").strip()      # how long the model stays in memory after a post, so a 16 GB machine has it back between posts


PLAY_COUNT_UNKNOWN = -1   # fetched, but the page had no count for that difficulty


# ---- how the bot names itself when it reads the wikis and chart databases. Left unset it carries
# this deployment's own address, so a copy of the bot identifies itself rather than whoever it was
# copied from; set it to say more, such as an address the site owners can write to.
USER_AGENT = os.getenv("USER_AGENT", "").strip() or f"rasmai/1.0 (+{PUBLIC_URL})"
# maimai DX NET serves its mobile pages to browsers and to nothing else, so those reads carry this
# instead. It is not a setting: a string that does not read as a browser gets the scraper turned away.
BROWSER_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


GUILD_ID = int(os.getenv("MAIMAI_GUILD_ID", "0") or 0)


PRESENCE_ENABLED = os.getenv("MAIMAI_PRESENCE", "true").lower() == "true"


PRESENCE_REGION = os.getenv("MAIMAI_PRESENCE_REGION", "intl").strip().lower()
