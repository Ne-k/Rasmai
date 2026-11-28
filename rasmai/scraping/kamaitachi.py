from typing import Any, Dict, List, Tuple
from urllib.parse import quote, urlencode
import json
import logging
import re
import time

import requests

from rasmai.bot.builders.kamaitachi import DIFFICULTY, JUDGEMENTS, LAMP_FOR
from rasmai.config import KAMAITACHI_CLIENT_ID, KAMAITACHI_CLIENT_SECRET, PUBLIC_URL, USER_AGENT

logger = logging.getLogger(__name__)

HOST = "https://kamai.tachi.ac"
REGION = "kamaitachi"    # what an account linked to a profile here is kept under: it has no maimai DX NET sign-in, so no token either
# the live server (v3) has no playtype in the path; the older docs show one and that address answers "Endpoint Not Found"
PATH = "/api/v1/users/{}/games/maimaidx/pbs/all"
USERNAME = re.compile(r"[A-Za-z0-9_-]{2,30}")
TIMEOUT = 30
DEADLINE = 90            # seconds for the whole read: the timeout alone is per chunk, and a slow trickle never trips it
MAX_BYTES = 25 * 1024 * 1024
MAX_PBS = 20000          # a player has at most one per chart, and the game has fewer than 2,000
TIERS = {name: tier for tier, name in DIFFICULTY.items()}
FC_FOR = {lamp: fc for fc, lamp in LAMP_FOR.items()}


# the client's redirect URI as registered on Kamaitachi; the token exchange is refused unless it matches exactly
CALLBACK = f"{PUBLIC_URL}/auth/kamaitachi/callback/"
RELINK = "Kamaitachi stopped letting Rasmai read your profile. Connect it again with `/login region:Kamaitachi`, or from the Account tab on your dashboard."


class KamaitachiError(Exception):
    """What went wrong reading a profile: ``kind`` is ``no_such_user``, ``relink`` or ``kamaitachi``, and the message is for the person."""

    def __init__(self, kind: str, message: str = "") -> None:
        super().__init__(message)
        self.kind = kind


def valid_username(username: Any) -> bool:
    return isinstance(username, str) and USERNAME.fullmatch(username) is not None


def _read(url: str, key: str = "") -> Dict[str, Any]:
    """The parsed answer; raises KamaitachiError for anything wrong, a 404 included, and ``relink`` when the key is refused."""
    started = time.monotonic()
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    try:
        # a redirect could lead anywhere, so none is followed; this host answers where it is asked
        response = requests.get(HOST + url, headers=headers, timeout=TIMEOUT, allow_redirects=False, stream=True)
    except requests.RequestException as error:
        logger.info("Kamaitachi unreachable: %s", error)
        raise KamaitachiError("kamaitachi", "Kamaitachi could not be reached.")
    try:
        if 300 <= response.status_code < 400:
            raise KamaitachiError("kamaitachi", "Kamaitachi sent the request somewhere else, which is not followed.")
        chunks: List[bytes] = []
        size = 0
        try:
            for chunk in response.iter_content(65536):
                size += len(chunk)
                if size > MAX_BYTES or time.monotonic() - started > DEADLINE:
                    raise KamaitachiError("kamaitachi", "That profile is too big or too slow to read.")
                chunks.append(chunk)
        except requests.RequestException as error:
            logger.info("Kamaitachi stopped answering: %s", error)
            raise KamaitachiError("kamaitachi", "Kamaitachi stopped answering.")
    finally:
        response.close()
    try:
        answer = json.loads(b"".join(chunks))
    except ValueError:
        answer = None
    if key and response.status_code in (401, 403):
        raise KamaitachiError("relink", RELINK)
    if not isinstance(answer, dict):
        raise KamaitachiError("kamaitachi", f"Kamaitachi answered {response.status_code} with something unreadable.")
    if response.status_code == 404:
        said = str(answer.get("description") or "")
        if "has not played" in said:
            raise KamaitachiError("kamaitachi", "That Kamaitachi profile has no maimai DX scores.")
        if "does not exist" in said:
            raise KamaitachiError("no_such_user")
        raise KamaitachiError("kamaitachi", "Kamaitachi has no maimai DX scores to read at the address it documents.")
    if response.status_code != 200 or answer.get("success") is not True or not isinstance(answer.get("body"), dict):
        raise KamaitachiError("kamaitachi", f"Kamaitachi answered {response.status_code}.")
    return answer["body"]


def fetch_pbs(username: str, key: str = "") -> Dict[str, Any]:
    """Every personal best of a maimai DX profile, with its songs and charts.

    With a key, this reads the profile the key belongs to, even after a rename; without one, it reads the public profile
    by that name, as accounts linked before the Kamaitachi sign-in do until they connect again.

    :param username: A Kamaitachi username, checked here against the allowed characters before it reaches a URL.
    :type username: str
    :param key: The API key Kamaitachi gave when the person linked.
    :type key: str
    :returns: The ``pbs``, ``songs`` and ``charts`` Kamaitachi sent.
    :rtype: Dict[str, Any]
    :raises KamaitachiError: When the user does not exist or has no maimai DX scores, when Kamaitachi refuses the key, or when Kamaitachi could not be read.
    """
    if key:
        return _read(PATH.format("me"), key)
    if not valid_username(username):
        raise KamaitachiError("no_such_user")
    return _read(PATH.format(quote(username, safe="")))


def link_ready() -> bool:
    return bool(KAMAITACHI_CLIENT_ID and KAMAITACHI_CLIENT_SECRET)


def authorize_url(state: str) -> str:
    """Kamaitachi's approval page for one link.

    :param state: Sent as ``context``; Kamaitachi hands it back with the code, so the callback knows whose link it is.
    :type state: str
    :rtype: str
    """
    return f"{HOST}/oauth/request-auth?{urlencode({'clientID': KAMAITACHI_CLIENT_ID, 'context': state})}"


def exchange_code(code: str) -> Tuple[str, str]:
    """Trade the code Kamaitachi handed back for the person's API key, and read whose profile it opens.

    :param code: The ``code`` from the callback.
    :type code: str
    :returns: The profile's username and the key.
    :rtype: Tuple[str, str]
    :raises KamaitachiError: ``kamaitachi`` when the code is refused or the answer cannot be read.
    """
    if not isinstance(code, str) or not 0 < len(code) <= 512:
        raise KamaitachiError("kamaitachi", "Kamaitachi sent no code back.")
    try:
        response = requests.post(f"{HOST}/api/v1/oauth/token", json={
            "client_id": KAMAITACHI_CLIENT_ID, "client_secret": KAMAITACHI_CLIENT_SECRET, "grant_type": "authorization_code",
            "redirect_uri": CALLBACK, "code": code,
        }, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}, timeout=TIMEOUT, allow_redirects=False)
        answer = response.json()
    except (requests.RequestException, ValueError) as error:
        logger.info("Kamaitachi token exchange failed: %s", type(error).__name__)
        raise KamaitachiError("kamaitachi", "Kamaitachi could not be reached.")
    body = answer.get("body") if isinstance(answer, dict) else None
    key = body.get("token") if isinstance(body, dict) else None
    if response.status_code != 200 or not isinstance(key, str) or not key:
        logger.info("Kamaitachi refused the code: %s", response.status_code)
        raise KamaitachiError("kamaitachi", "Kamaitachi did not accept the link. Try connecting again.")
    username = _read("/api/v1/users/me", key).get("username")
    if not valid_username(username):
        raise KamaitachiError("kamaitachi", "Kamaitachi did not say whose profile this is.")
    return username, key


def pb_rows(body: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Personal bests as plain rows to match against the chart database; a best that cannot be read is left out.

    :param body: What :func:`fetch_pbs` returned.
    :type body: Dict[str, Any]
    :returns: Per best: ``titles`` (the song's title and its other names), ``type``, ``tier``, ``level``, ``percent``,
        ``fc`` as Rasmai writes it, ``time`` in milliseconds or None, and ``judgements`` when all five were sent.
    :rtype: List[Dict[str, Any]]
    """
    def table(name: str, key: str) -> Dict[str, Any]:
        rows = body.get(name)
        return {str(row.get(key) or row.get("id")): row for row in rows if isinstance(row, dict)} if isinstance(rows, list) else {}

    # a chart carries its song inside it and is keyed by chartID; the `songs` list is the fallback
    songs, charts = table("songs", "id"), table("charts", "chartID")
    out: List[Dict[str, Any]] = []
    for pb in (body.get("pbs") if isinstance(body.get("pbs"), list) else [])[:MAX_PBS]:
        if not isinstance(pb, dict) or not isinstance(pb.get("scoreData"), dict):
            continue
        chart = charts.get(str(pb.get("chartID")))
        inside = (chart or {}).get("song")
        song = inside if isinstance(inside, dict) else songs.get(str((chart or {}).get("songID") or pb.get("songID")))
        data = pb["scoreData"]
        difficulty = str((chart or {}).get("difficulty") or "")
        dx = difficulty.startswith("DX ")
        tier = TIERS.get(difficulty[3:] if dx else difficulty)
        titles = [str(t) for t in [(song or {}).get("title"), *((song or {}).get("altTitles") or [])] if isinstance(t, str) and t.strip()]
        if not titles or tier is None or isinstance(data.get("percent"), bool) or not isinstance(data.get("percent"), (int, float)):
            continue
        counts = data.get("judgements") if isinstance(data.get("judgements"), dict) else {}
        judged = {key: counts.get(key) for key in JUDGEMENTS}
        when = pb.get("timeAchieved")
        out.append({
            "titles": titles, "type": "dx" if dx else "std", "tier": tier, "level": str((chart or {}).get("level") or ""),
            "percent": float(data["percent"]), "fc": FC_FOR.get(str(data.get("lamp") or ""), ""),
            "time": when if isinstance(when, (int, float)) and not isinstance(when, bool) else None,
            "judgements": judged if all(isinstance(v, int) and not isinstance(v, bool) and v >= 0 for v in judged.values()) else None,
        })
    return out
