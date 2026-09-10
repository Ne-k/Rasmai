from typing import Dict
import re
import urllib.parse

from rasmai.config import get_public_base_url
from rasmai.storage.db import issue_login_code, login_code_expiry
from rasmai.security import create_opaque_user_id


def build_login_link_payload(opaque_user_id: str, code: str, region: str) -> Dict[str, str]:
    """Everything the connect page needs, given an already-issued login code.

    :param code: The login code.
    :type code: str
    :param region: ``"intl"``, ``"jp"`` or ``"cn"``.
    :type region: str
    :rtype: Dict[str, str]
    """
    base_url = get_public_base_url()
    script_url = f"{base_url}/api/login.js"
    return {
        "code": code,
        "expiresAt": login_code_expiry().isoformat(),
        "opaqueUserId": opaque_user_id,
        "loginLink": f"https://lng-tgk-aime-gw.am-all.net/common_auth/#code={code}&user={opaque_user_id}&region={region}",
        "scriptUrl": script_url,
        "bookmarklet": f"javascript:void(function(d){{var s=d.createElement(\"script\");s.src=\"{script_url}\";d.body.append(s);}}(document))",
        "connectUrl": f"{base_url}/connect/?code={code}&user={opaque_user_id}",
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
