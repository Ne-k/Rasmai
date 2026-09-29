from typing import Any, Dict, Sequence

from rasmai.engine.plates import plate_standing
from rasmai.images.posters import _esc
from rasmai.images.pages.common import _image

# how many segments a bar is cut into: enough to see a tenth move, few enough to read at preview size
SEGMENTS = 20


def _bar(goal: Dict[str, Any]) -> str:
    required, met = int(goal["required"] or 0), int(goal["met"] or 0)
    lit = 0 if not required else min(SEGMENTS, int(SEGMENTS * met / required))
    if met and not lit:
        lit = 1          # a single chart met still shows, so a start never reads as nothing
    cells = "".join(f'<i class="{"on" if n < lit else ""}"></i>' for n in range(SEGMENTS))
    done = " done" if required and met >= required else ""
    return (f'<div class="plate-goal g-{_esc(goal["label"]).lower()}{done}"><span class="k">{_esc(goal["label"])}</span>'
            f'<span class="seg">{cells}</span><span class="n"><b>{met}</b>/{required}</span></div>')


def plates_image_html(plates: Sequence[Dict[str, Any]], player_name: str, avatar_b64: str, date_text: str = "") -> str:
    """Every plate as a tile: the kanji on a cream chip, then one segmented bar per condition.

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
    tiles = ""
    for plate in plates:
        kanji = plate["key"] if plate["key"] != plate["name"] else ""
        chip = f'<span class="plate-chip">{_esc(kanji)}</span>' if kanji else f'<span class="plate-chip word">{_esc(plate["key"])}</span>'
        tiles += (f'<div class="plate-tile">{chip}<div class="plate-name">{_esc(plate["name"])}'
                  f'<small>{_esc(plate["reading"]) + " &middot; " if plate["reading"] else ""}{plate["required"]} charts</small></div>'
                  f'<div class="plate-goals">{"".join(_bar(goal) for goal in plate["goals"])}</div></div>')
    earned, _closest = plate_standing(plates)
    played = sum(int(plate["played"]) for plate in plates if plate["key"] != "舞")
    asked = sum(int(plate["required"]) for plate in plates if plate["key"] != "舞")
    counters = [("Plates", str(len(plates))), ("Charts played", f"{played}/{asked}")]
    body = f'<div class="section-label">Version plates &middot; every chart of a version, BASIC to MASTER</div><div class="plate-grid">{tiles}</div>'
    return _image("Plates", player_name, avatar_b64, counters, str(earned), "plates earned", body, date_text)
