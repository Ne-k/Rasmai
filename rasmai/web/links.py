from typing import Dict
import re
import urllib.parse

from rasmai.config import get_public_base_url
from rasmai.storage.db import issue_login_code, login_code_expiry
from rasmai.security import create_opaque_user_id

# signing in here with auto login ticked is what sets the cookie the person copies; a signed-in browser lands on maimai DX NET
GATEWAY_LOGIN = "https://lng-tgk-aime-gw.am-all.net/common_auth/login?site_id=maimaidxex&redirect_url=https://maimaidx-eng.com/maimai-mobile/&back_url=https://maimai.sega.com/"


def build_login_link_payload(opaque_user_id: str, code: str, region: str) -> Dict[str, str]:
    """Everything the connect page needs, given an already-issued login code.

    :param code: The login code.
    :type code: str
    :param region: ``"intl"``, ``"jp"`` or ``"cn"``.
    :type region: str
    :rtype: Dict[str, str]
    """
    base_url = get_public_base_url()
    # both are linked on the connect page itself: a Japan account with its SEGA ID, an International one with the gateway's
    # sign-in cookie, which the person copies from their own browser since SEGA hid it from scripts
    return {
        "code": code,
        "expiresAt": login_code_expiry().isoformat(),
        "opaqueUserId": opaque_user_id,
        "method": "segaid" if region == "jp" else "cookie",
        "loginLink": "" if region == "jp" else GATEWAY_LOGIN,
        "connectUrl": f"{base_url}/connect/?code={code}&user={opaque_user_id}",
        # what the Aime sign-in helper extension is given: the connect page's own credential, in the shape /api/link reads
        "helperLink": "" if region == "jp" else f"{base_url}/api/link/{code}.{opaque_user_id}",
        "helperInstall": f"{base_url}/extension",       # where the extension is added from; the site sends it on to the store
    }


def build_login_session_payload(user_id: str, region: str) -> Dict[str, str]:
    return build_login_link_payload(create_opaque_user_id(user_id), issue_login_code(user_id, region), region)


# ---------------------------------------------------------------- pages on the site, for Discord embeds

TIER_CODE = {"basic": "bas", "advanced": "adv", "expert": "exp", "master": "mas", "remaster": "rem", "utage": "utg"}


def cover_stem(cover: str) -> str:
    """The jacket file's name without its extension: the short, safe id the site resolves a chart from.

    :param cover: The jacket file name.
    :type cover: str
    :rtype: str
    """
    name = str(cover or "").split("/")[-1].split("?")[0]
    stem = name.rsplit(".", 1)[0] if "." in name else name
    return stem if re.fullmatch(r"[A-Za-z0-9_-]{1,80}", stem) else ""


def chart_url(title: str, chart_type: str = "", difficulty: str = "", cover: str = "") -> str:
    """The Look up page for a chart: a short /c/ path by jacket id when the chart has one, else by title.

    :param title: The song title.
    :type title: str
    :param chart_type: ``"std"`` or ``"dx"``.
    :type chart_type: str
    :param difficulty: The difficulty tier, such as ``"master"``.
    :type difficulty: str
    :param cover: The jacket file name.
    :type cover: str
    :rtype: str
    """
    base_url = get_public_base_url()
    stem = cover_stem(cover)
    kind = "dx" if str(chart_type).lower() == "dx" else "std"
    if stem and difficulty:
        return f"{base_url}/c/{stem}/{kind}/{TIER_CODE.get(str(difficulty).lower(), 'mas')}"
    query = f"chart={urllib.parse.quote(str(title), safe='')}"
    if chart_type:
        query += f"&type={kind}"
    if difficulty:
        query += f"&difficulty={urllib.parse.quote(str(difficulty).lower(), safe='')}"
    return f"{base_url}/me/?{query}#chart"


def area_url(name: str = "") -> str:
    """The Areas tab, opened on one area when a name is given.

    :param name: The name to look up.
    :type name: str
    :rtype: str
    """
    base_url = get_public_base_url()
    return f"{base_url}/me/?area={urllib.parse.quote(str(name), safe='')}#areas" if name else f"{base_url}/me/#areas"
