from typing import Any, Callable, Dict, Tuple
import asyncio
import logging

import requests

from rasmai.config import INTERNAL_API_SECRET, TUNNEL_ORIGIN
from rasmai.storage.db import dev_flags_get, dev_flags_set, link_bots_get, link_bots_set, oauth_app_block, oauth_app_get, oauth_app_set, oauth_apps
from rasmai.web import oauth
from rasmai.web.grants import clean_origin, public_key

logger = logging.getLogger(__name__)

Answer = Tuple[int, Dict[str, Any]]


def control_payload() -> Dict[str, Any]:
    """What the controls on the dashboard's developer page show: every switch, and what each action has to offer.

    :rtype: Dict[str, Any]
    """
    from rasmai.bot import core
    from rasmai.bot.commands.dev import switchable
    from rasmai.bot.tasks import presence
    from rasmai.scraping import news
    region = core.watch.region
    return {
        "ok": True,
        "maimai": {"region": region, "reachable": bool(core.watch.reachable), "said": presence._said.get(region) or ""},
        "flags": dev_flags_get(),
        "commands": switchable(),
        "mirrors": [{"handle": handle, "host": news.urlparse(base).hostname or ""} for handle, base in sorted(news._working.items())],
        "bots": "\n".join(f"{name} {origin}" for origin, name in link_bots_get().items()),
        "grantKey": public_key(),
        "reviews": oauth.REVIEW,
        # every app, newest first: what a player would be shown of it, and what the review was shown
        "apps": [{"id": app["id"], "name": app["name"], "by": app["owner_name"], "userId": app["user_id"], "website": app["website"],
                  "privacy": app["privacy"], "review": app["review"], "blocked": bool(app["blocked"]),
                  "sites": list(dict.fromkeys(clean_origin(uri) for uri in app["redirects"] if not oauth._local(uri))),
                  "stamp": oauth.review_stamp(app)} for app in reversed(oauth_apps())],
    }


def _on_loop(work: Callable[[], Any], wait: float = 10) -> Any:
    """Run something on the bot's own loop from this thread and hand back what it gave; a coroutine it returns is awaited there."""
    from rasmai.bot.core import bot
    if not bot.is_ready():
        raise RuntimeError("the bot is not running")

    async def run() -> Any:
        given = work()
        return await given if asyncio.iscoroutine(given) else given
    return asyncio.run_coroutine_threadsafe(run(), bot.loop).result(timeout=wait)


def _restart_site() -> Tuple[bool, str]:
    # the site's own address from this side: on the compose network the one the tunnel is pointed at
    try:
        answer = requests.post(f"{TUNNEL_ORIGIN}/api/internal/restart", headers={"X-Rasmai-Internal": INTERNAL_API_SECRET}, timeout=10)
    except requests.RequestException as error:
        return False, f"The website could not be reached at {TUNNEL_ORIGIN}: {type(error).__name__}."
    if answer.status_code == 200:
        return True, "The main website is restarting and answers again within about half a minute. The developer portal's own container is not restarted."
    return False, f"The website refused (HTTP {answer.status_code}). Both halves must share RASMAI_INTERNAL_SECRET, and the site must carry /api/internal/restart."


async def _resync() -> bool:
    from rasmai.bot import core
    marker = core.DATABASE_PATH.parent / "commands.sha256"
    try:
        marker.unlink()   # the sync skips when the definitions match the last sync; without the record they cannot
    except OSError:
        pass
    await core.sync_commands_if_changed()
    # the record is written only by a sync that went through: Discord refusing one is logged, not raised
    return marker.exists()


def _restart_bot() -> None:
    from rasmai.bot.core import bot
    # a moment later, so this answer gets out first; the process ends cleanly, which the container's restart policy answers by starting it again
    asyncio.get_running_loop().call_later(1, lambda: asyncio.ensure_future(bot.close()))


def control_act(payload: Dict[str, Any]) -> Answer:
    """One action from the dashboard's developer page, by the developer. Each answers ``said``: what happened, in words.

    :param payload: ``action`` and what that action needs.
    :type payload: Dict[str, Any]
    :rtype: Answer
    """
    from rasmai.bot import core
    from rasmai.bot.commands.dev import parse_bots, switchable
    action = payload.get("action")
    on = payload.get("on")
    said = ""
    # a switch is set to what was asked for, never to what a missing word happens to mean
    if action in ("maintenance", "deletions") and not isinstance(on, bool):
        return 400, {"ok": False, "error": "bad_action"}
    if action == "maintenance":
        dev_flags_set(maintenance=on)
        said = ("Maintenance is on: every command answers that Rasmai is under maintenance, and the presence says so within a minute."
                if on else "Maintenance is off: commands answer again.")
    elif action == "deletions":
        dev_flags_set(deletions=on)
        said = ("Deletions resumed: the hourly sweep warns and deletes again from its next run." if on else
                "Deletions held: the hourly sweep deletes nobody and sends no warning, and every expired account's deadline moves an hour for each hour held.")
    elif action == "commands":
        chosen = payload.get("disabled")
        if not isinstance(chosen, list) or any(name not in switchable() for name in chosen):
            return 400, {"ok": False, "error": "bad_commands"}
        dev_flags_set(disabled=sorted(set(chosen)))
        said = f"Switched off: {', '.join(f'/{name}' for name in sorted(set(chosen))) or 'nothing'}. Everyone but you is told so when they run one."
    elif action == "bots":
        bots, refused = parse_bots(str(payload.get("bots") or "")[:4000])
        link_bots_set(bots)
        said = f"{len(bots)} verified bot(s) besides Rasmai." + (f" Not saved, since they are not 'Name https://site': {'; '.join(refused)}" if refused else "")
    elif action in ("block", "unblock", "review"):
        app = oauth_app_get(str(payload.get("id") or ""))
        if not app:
            return 404, {"ok": False, "error": "no_such_app"}
        if action == "review":
            verdict = payload.get("verdict")
            # what is approved is what was shown: an app that changed since the page was drawn is looked at again first
            if not oauth.REVIEW or verdict not in ("verified", "rejected", "none") or payload.get("stamp") != oauth.review_stamp(app) \
                    or app["review"] != ("verified" if verdict == "none" else "pending"):
                return 409, {"ok": False, "error": "changed"}
            oauth_app_set(app["id"], review=verdict)
            said = {"verified": f"{app['name']} is verified.", "rejected": f"{app['name']} was rejected.", "none": f"{app['name']} is no longer verified."}[verdict]
        else:
            oauth_app_block(app["id"], action == "block")
            said = (f"{app['name']} is blocked: nobody can approve it, and the sign-ins it was waiting on are deleted."
                    if action == "block" else f"{app['name']} is unblocked.")
    elif action == "restart_site":
        done, said = _restart_site()
        if not done:
            return 502, {"ok": False, "error": "failed", "said": said}
    elif action in ("news", "sweep", "resync", "restart_bot"):
        # these act on the running bot, on its own loop; with no bot running there is nothing to act on
        try:
            if action == "news":
                said = ("Every followed X account is being read now, one after another, and any new post goes out as usual."
                        if _on_loop(core.news_watch.read_now) else "The X news loop is not running, so nothing was read. A restart starts it again.")
            elif action == "sweep":
                # the loop is restarted rather than its body run beside it: two sweeps at once would warn the same people twice.
                # One that has died is started instead: restarting a loop that is not running does nothing
                sweep = core._expired_account_sweep
                _on_loop(lambda: sweep.restart() if sweep.is_running() else sweep.start())
                said = "The sweep is running now, and the next automatic one is an hour from now."
            elif action == "resync":
                if not _on_loop(_resync, wait=60):
                    return 502, {"ok": False, "error": "failed", "said": "The sync did not go through. The bot's log says why."}
                said = "Commands synced with Discord. Global ones can take up to an hour to show everywhere."
            else:
                _on_loop(_restart_bot)
                said = "The bot is restarting. It is gone for about a minute; Docker starts it again."
        except TimeoutError:
            # asked, and still at it: Discord can make a sync wait longer than this page does
            said = "Asked, and it is still running. Give it a minute."
        except Exception as error:
            logger.warning("the %s action from the dashboard could not reach the bot: %s", action, type(error).__name__)
            return 503, {"ok": False, "error": "bot_down"}
    else:
        return 400, {"ok": False, "error": "bad_action"}
    logger.warning("%s by the developer from the dashboard: %s", action, said)
    return 200, {"ok": True, "said": said}
