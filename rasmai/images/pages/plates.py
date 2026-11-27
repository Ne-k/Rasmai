from typing import Any, Dict, Optional, Sequence

from rasmai.engine.plates import GOALS, HUES, PLATE_KEYS, chance_text, plate_standing
from rasmai.images.posters import CoverFn, _esc, kind_mark, mark, panel, stats, tier, tier_mark
from rasmai.images.pages.common import _image

# an earned condition is stamped with the mark the bot gives that lamp or rank; Clear has none, so its ring fills
WON = {"FC": "lamp_fc", "SSS": "rank_sss", "AP": "lamp_ap", "FDX": "lamp_fdx"}


def _cond(label: str, goal: Optional[Dict[str, Any]], nearest: bool) -> str:
    key = _esc(label)
    if goal is None:
        # a plate without this condition keeps the place, so the conditions line up across the wall
        return f'<div class="pl-cond none"><span class="pl-ring"><span>{key}</span></span><small>none</small></div>'
    required, met = int(goal["required"] or 0), int(goal["met"] or 0)
    figure = f"<small><b>{met}</b>/{required}</small>"
    if required and met >= required:
        stamp = mark(WON[label]) if label in WON else f'<span class="pl-ring" style="--p:100%"><span>{key}</span></span>'
        return f'<div class="pl-cond won c-{key.lower()}">{stamp}{figure}</div>'
    # a single chart met still shows, so a start never reads as nothing
    share = max(4, round(100 * met / required)) if met and required else 0
    return (f'<div class="pl-cond c-{key.lower()}{" near" if nearest else ""}"><span class="pl-ring" style="--p:{share}%"><span>{key}</span></span>'
            f'{figure}</div>')


def _prize(plate: Dict[str, Any], labels: Sequence[str], closest: Optional[tuple], shape: str = "") -> str:
    first, second = plate.get("hue") or HUES["舞"]
    goals = {goal["label"]: goal for goal in plate["goals"]}
    near = closest is not None and closest[0] is plate
    face = (f'<span class="pl-kanji">{_esc(plate["key"])}</span>' if plate["key"] != plate["name"]
            else f'<span class="pl-word">{_esc(plate["key"])}</span>')
    reading = f'{_esc(plate["reading"])} · ' if plate["reading"] else ""
    tag = ""
    if near:
        goal = closest[1]
        tag = f'<span class="pl-next">Nearest: <b>{int(goal["required"]) - int(goal["met"])}</b> to {_esc(goal["label"])}</span>'
    conds = "".join(_cond(label, goals.get(label), near and closest[1]["label"] == label) for label in labels)
    return (f'<div class="pl-prize {shape}" style="--p1:{first};--p2:{second}">'
            f'<div class="pl-face">{face}<span class="pl-tag"><b>{_esc(plate["name"])}</b><small>{reading}{plate["required"]} charts</small></span></div>'
            f'<div class="pl-conds" style="--n:{len(labels)}">{conds}</div>{tag}</div>')


def _labels(group: Sequence[Dict[str, Any]]) -> list:
    return [label for _goal, label in GOALS if any(goal["label"] == label for plate in group for goal in plate["goals"])]


def plates_image_html(plates: Sequence[Dict[str, Any]], player_name: str, avatar_b64: str, date_text: str = "") -> str:
    """The prize wall: every plate as a ticket stood on end in its version's two colours, the kanji on the face and a ring per
    condition below the tear, an earned condition stamped with its lamp or rank mark. A banner holds the count, the earned marks
    and the nearest plate's nameplate; under it the plates up to FiNALE, Mai and the DX plates each lie on a sheet of their own.

    :param plates: The plates as ``plate_overview`` describes them.
    :type plates: Sequence[Dict[str, Any]]
    :param player_name: The player's name on maimai DX NET.
    :type player_name: str
    :param avatar_b64: The player's avatar, base64 encoded.
    :type avatar_b64: str
    :param date_text: The date to print on the image.
    :type date_text: str
    :rtype: str
    """
    mai = [plate for plate in plates if plate["key"] == "舞"]
    versions = [plate for plate in plates if plate["key"] != "舞"]
    older = [plate for plate in versions if plate["key"] in PLATE_KEYS and PLATE_KEYS[plate["key"]].versions[-1] < "200"]
    newer = [plate for plate in versions if plate not in older]
    earned, closest = plate_standing(plates)
    rule = "every chart of a version, BASIC to MASTER"

    def wall(group: Sequence[Dict[str, Any]]) -> str:
        # two full rolls: an odd plate out, the newest, takes two places
        labels = _labels(group)
        tiles = "".join(_prize(plate, labels, closest, "wide" if len(group) > 1 and len(group) % 2 and plate is group[-1] else "") for plate in group)
        return f'<div class="pl-wall" style="--across:{(len(group) + 1) // 2}">{tiles}</div>'

    top = ""
    if older:
        top += panel("pink run", "maimai to FiNALE", wall(older), f"{len(older)} plates · {rule}")
    if mai:
        top += panel("gold run pl-mai", "Mai", _prize(mai[0], _labels(mai), closest, "tall"), "includes Re:MASTER")
    body = f'<div class="pl-top">{top}</div>' if older and mai else top
    if newer:
        body += panel("cyan run", "maimai DX", wall(newer), f"{len(newer)} plates · {rule}")
    pairs = [goal for plate in plates for goal in plate["goals"] if goal["required"]]
    played = sum(int(plate["played"]) for plate in versions)
    asked = sum(int(plate["required"]) for plate in versions)
    won = [goal["label"] for goal in pairs if goal["met"] >= goal["required"]]
    tally = "".join(f'<span>{mark(WON[label]) if label in WON else f"<em>{label}</em>"}{won.count(label)}</span>' for _goal, label in GOALS)
    near = ""
    if closest:
        plate, goal = closest
        art = plate_art(plate["key"], plate["name"], goal["goal"], goal["label"], False, f'{goal["met"]}/{goal["required"]} {goal["label"]}')
        near = (f'<div class="pl-near"><span>Nearest<b>{int(goal["required"]) - int(goal["met"])}</b><small>charts to go</small></span>'
                f'<div class="plate-hero">{art}</div></div>')
    banner = (f'<div class="banner"><div class="sum"><span><b>{earned}</b><small>earned</small></span><i>+</i><span>{len(pairs) - earned}<small>still open</small></span>'
              f'<i>=</i><span>{len(pairs)}<small>plates in all</small></span></div>'
              f'{stats((("Versions", str(len(plates))), ("Charts played", f"{played}/{asked}")))}'
              f'<div class="tally pl-tally">{tally}</div>{near}</div>')
    return _image("Plates", player_name, avatar_b64, str(earned), "plates earned", banner + body, date_text)


GOAL_CLASSES = {"覇者": "clear", "極": "fc", "将": "sss", "神": "ap", "舞舞": "fdx"}


def plate_art(key: str, name: str, goal: str, label: str, earned: bool, caption: str = "") -> str:
    """Rasmai's nameplate for one plate and condition: the version's colours, the kanji on a cream chip and the plate's name
    in the condition's finish, greyed until it is earned. The site draws the same plate (web/components/dash/PlateArt.tsx).

    :param key: The plate's kanji, or the version's name while it has none.
    :type key: str
    :param name: The version or versions it covers.
    :type name: str
    :param goal: The condition's kanji, such as ``"極"``.
    :type goal: str
    :param label: The condition as the bot prints it, such as ``"FC"``.
    :type label: str
    :param earned: Whether every chart already meets it.
    :type earned: bool
    :param caption: A line under the name, such as the count met.
    :type caption: str
    :rtype: str
    """
    first, second = HUES.get(key, HUES["舞"])
    kanji = key if len(key) == 1 else ""
    # 覇者 is a plate of its own name; a version with no kanji yet shows its condition
    title = "覇者" if goal == "覇者" else f"{kanji}{goal}" if kanji else label
    chip = f'<span class="pa-chip">{_esc(kanji)}</span>' if kanji else f'<span class="pa-chip word">{_esc(key)}</span>'
    return (f'<div class="pa g-{GOAL_CLASSES.get(goal, "fc")}{"" if earned else " locked"}" style="--p1:{first};--p2:{second}">'
            f'{chip}<span class="pa-mid"><b>{_esc(name)}</b><small>{_esc(caption)}</small></span>'
            f'<span class="pa-title">{_esc(title)}</span></div>')



def plate_detail_image_html(detail: Dict[str, Any], player_name: str, avatar_b64: str, rows: Sequence[Dict[str, Any]],
                            heading: str = "Closest first", date_text: str = "", cover_html: Optional[CoverFn] = None) -> str:
    """One prize up close: a banner of how far along it is, then a sheet with its nameplate as the hero at the head of the rolls
    of tickets it still needs, each with its difficulty's lantern and its chance on the stub, under the numbers the embed links
    them by.

    :param detail: The plate as ``plate_missing`` describes it.
    :type detail: Dict[str, Any]
    :param player_name: The player's name on maimai DX NET.
    :type player_name: str
    :param avatar_b64: The player's avatar, base64 encoded.
    :type avatar_b64: str
    :param rows: The charts to draw, in the order the embed numbers them.
    :type rows: Sequence[Dict[str, Any]]
    :param heading: What the order is, over the rows.
    :type heading: str
    :param date_text: The date to print on the image.
    :type date_text: str
    :param cover_html: Draws a chart's jacket; without it the tickets carry no jacket.
    :type cover_html: Optional[CoverFn]
    :rtype: str
    """
    met, required = int(detail["met"]), int(detail["required"])
    label = _esc(detail["label"])
    caption = f"{detail['reading']} · " if detail["reading"] else ""
    art = plate_art(detail["key"], detail["name"], detail["goal"], detail["label"], met >= required,
                    f"{caption}{detail['label']} on {required} charts")
    more = len(detail["missing"]) - len(rows)
    odds = any(r.get("chance") is not None for r in rows)
    tickets = ""
    for n, r in enumerate(rows, 1):
        name, ink = tier(r["difficulty"])
        chance = f'<strong class="{r["band"]}">{chance_text(r["chance"])}</strong>' if r.get("chance") is not None else ""
        jacket = cover_html(r.get("cover", ""), "track-jacket") if cover_html else ""
        tickets += (
            f'<div class="track pl-ticket{" pl-jacketed" if jacket else ""}" style="--tier:{ink}"><div class="track-stub"><b>{n}</b>{tier_mark(r["difficulty"])}<small>{r["constant"]:.1f}</small>{chance}</div>'
            f'<div class="track-body"><div class="track-name"><b>{_esc(r["title"])}</b>{kind_mark(r["type"])}</div>{jacket}'
            f'<div class="track-score"><b class="{"" if r["played"] else "dim"}">{_esc(r["need"]) if r["played"] else "never played"}</b><small>{_esc(name)} {_esc(r["level"])}</small></div></div></div>')
    # the nameplate takes the first two places of the first roll, and a piece spanning the places a short last roll leaves closes it
    spare = -(2 + len(rows)) % 4 if rows else 0
    closer = ""
    if spare:
        closer = (f'<div class="pl-closer" style="grid-column:span {spare}"><p><b>Stub:</b> row, difficulty, constant'
                  f'{", odds of " + label if odds else ""}</p></div>')
    hero = f'<div class="plate-hero pl-hero{"" if rows else " alone"}" style="grid-column:span {2 if rows else 1}">{art}</div>'
    banner = (f'<div class="banner"><div class="sum"><span><b>{met}</b><small>{label} met</small></span><i>+</i><span>{required - met}<small>to go</small></span>'
              f'<i>=</i><span>{required}<small>charts on the plate</small></span></div>'
              f'<div class="pl-meter"><i style="width:{100 * met / required if required else 0:.1f}%"></i><span>{100 * met / required if required else 0:.1f}%</span></div>'
              + ('<div class="pl-key"><span class="likely">60%+<small>likely</small></span><span class="maybe">25%+<small>maybe</small></span>'
                 '<span class="long">&lt;25%<small>long shot</small></span></div>' if odds else "")
              + "</div>")
    note = heading[:1].lower() + heading[1:] + (f" · {more} more after these" if more > 0 else "")
    body = banner + panel("cyan run", "Still needed" if rows else "Earned", f'<div class="tracks pl-roll" style="--across:{4 if rows else 1}">{hero}{tickets}{closer}</div>',
                          note if rows else f"every chart meets {detail['label']}")
    kanji = detail["key"] if len(detail["key"]) == 1 else ""
    # the plate as the game names it: 祭極, 覇者, or the version and condition while it has no kanji
    name = "覇者" if detail["goal"] == "覇者" else f'{kanji}{detail["goal"]}' if kanji else f'{detail["key"]} {detail["label"]}'
    return _image(f"Plate · {name}", player_name, avatar_b64, f"{met}/{required}", f"{detail['label']} met", body, date_text)
