from dataclasses import dataclass
import math
from typing import Any, Dict, FrozenSet, Iterable, List, Optional, Tuple

from rasmai.engine.analysis import ChartIndex, ChartRef, DIFFICULTY_ORDER
from rasmai.engine.analysis.planning.predict import chart_prediction
from rasmai.engine.analysis.rating import ACHIEVEMENT_CAP, _normal_cdf


# The rules are the maimai 攻略 wiki's list of 制覇系 plates, https://gamerch.com/maimai/533650 (read
# 28 Sep 2026), which gives each plate as "<version> 全曲/BASIC～MASTER/<condition>". The per-chart
# version a DX chart of an older song belongs to comes from dxrating's dxdata (see rasmai/scraping/dxdata.py).

# Every version in order: the otoge-db code, the name the site shows, and the plate's kanji.
# MAGiCAL opened on 17 Sep 2026 and the wiki lists no plate for it yet, so it goes by its name.
VERSIONS: Tuple[Tuple[str, str, str], ...] = (
    ("100", "maimai", "真"), ("110", "maimai PLUS", "真"), ("120", "GreeN", "超"), ("130", "GreeN PLUS", "檄"),
    ("140", "ORANGE", "橙"), ("150", "ORANGE PLUS", "暁"), ("160", "PiNK", "桃"), ("170", "PiNK PLUS", "櫻"),
    ("180", "MURASAKi", "紫"), ("185", "MURASAKi PLUS", "菫"), ("190", "MiLK", "白"), ("195", "MiLK PLUS", "雪"),
    ("199", "FiNALE", "輝"), ("200", "maimai DX", "熊"), ("205", "DX PLUS", "華"), ("210", "Splash", "爽"),
    ("215", "Splash PLUS", "煌"), ("220", "UNiVERSE", "宙"), ("225", "UNiVERSE PLUS", "星"), ("230", "FESTiVAL", "祭"),
    ("235", "FESTiVAL PLUS", "祝"), ("240", "BUDDiES", "双"), ("245", "BUDDiES PLUS", "宴"), ("250", "PRiSM", "鏡"),
    ("255", "PRiSM PLUS", "彩"), ("260", "CiRCLE", "丸"), ("265", "CiRCLE PLUS", "廻"), ("270", "MAGiCAL", ""),
)

# dxrating spells the first two DX versions its own way
_OTHER_NAMES = {"maimaiでらっくす": "200", "maimaiでらっくす PLUS": "205", "maimai でらっくす": "200",
                "maimai でらっくす PLUS": "205"}

# The conditions, hardest last, with the label the bot and the site print. 覇者 (clear, 80%) only
# exists on the 舞 plate; 将 is SSS, 100.0000% and up.
GOALS: Tuple[Tuple[str, str], ...] = (("覇者", "Clear"), ("極", "FC"), ("将", "SSS"), ("神", "AP"), ("舞舞", "FDX"))
GOAL_LABELS = dict(GOALS)

# the names players use for the plates in English: the kanji's reading, then the condition's ("Shin Kiwami")
READINGS = {
    "真": "Shin", "超": "Chou", "檄": "Geki", "橙": "Dai", "暁": "Gyou", "桃": "Tou", "櫻": "Ou", "紫": "Shi",
    "菫": "Sumire", "白": "Haku", "雪": "Setsu", "輝": "Ki", "熊": "Kuma", "華": "Hana", "爽": "Sou", "煌": "Kou",
    "宙": "Sora", "星": "Hoshi", "祭": "Matsuri", "祝": "Shuku", "双": "Sou", "宴": "Utage", "鏡": "Kyou", "彩": "Sai",
    "丸": "Maru", "廻": "Kai", "舞": "Mai",
}
GOAL_READINGS = {"覇者": "Hasha", "極": "Kiwami", "将": "Shou", "神": "Kami", "舞舞": "Maimai"}

# Rasmai's own colour pair for each plate's nameplate, read off the version's name (GreeN green, MiLK white, FESTiVAL
# fireworks violet and pink); CiRCLE, CiRCLE PLUS and MAGiCAL take the site backdrop's ring colours, Mai the site's pink to gold
HUES = {
    "真": ("#2f86e8", "#8fd3ff"), "超": ("#2fae5e", "#a6e36b"), "檄": ("#17885a", "#4fd1a0"), "橙": ("#f07a12", "#ffc04d"),
    "暁": ("#e8502e", "#ffb347"), "桃": ("#f0508f", "#ffb3d1"), "櫻": ("#e8689f", "#ffd1e3"), "紫": ("#7d44d6", "#c49bff"),
    "菫": ("#5b43c9", "#a58cff"), "白": ("#b9ae98", "#fffaf0"), "雪": ("#78b8de", "#eef9ff"), "輝": ("#d19a1c", "#ffe27a"),
    "熊": ("#2460d8", "#5cd3e8"), "華": ("#d03f7c", "#ffa3c8"), "爽": ("#139fd0", "#7ff0ff"), "煌": ("#2477d8", "#ffd84d"),
    "宙": ("#30237a", "#7b5cff"), "星": ("#22338a", "#5cd3e8"), "祭": ("#5d31c4", "#ff4fa3"), "祝": ("#c8337d", "#ffb347"),
    "双": ("#f08a12", "#ff4f6d"), "宴": ("#d63c22", "#ffcf3a"), "鏡": ("#3f68e8", "#c58bff"), "彩": ("#f05ea4", "#7fd8ff"),
    "丸": ("#ff4fa3", "#3cc8e8"), "廻": ("#8f72f0", "#3cc8e8"), "MAGiCAL": ("#14a06a", "#e8b422"), "舞": ("#ff3d8f", "#f0c04a"),
}

_FC = {"FC", "FC+", "AP", "AP+"}
_AP = {"AP", "AP+"}
_FDX = {"FDX", "FDX+"}


@dataclass(frozen=True)
class Plate:
    key: str                                  # the kanji, or the version's name while it has none
    versions: Tuple[str, ...]                 # otoge-db codes the plate covers
    goals: Tuple[str, ...]
    std_only: bool = False
    remaster: bool = False                    # Re:MASTER counts; only the 舞 plate asks for it
    excluded: FrozenSet[Tuple[str, str]] = frozenset()      # (title, chart type) the plate leaves out

    @property
    def name(self) -> str:
        names = {code: name for code, name, _kanji in VERSIONS}
        if len(self.versions) > 2:
            return f"{names[self.versions[0]]} to {names[self.versions[-1]]}, standard charts"
        first, *rest = [names[code] for code in self.versions]
        return " + ".join([first] + [name.removeprefix(first + " ") for name in rest])     # "maimai + PLUS"

    @property
    def reading(self) -> str:
        return READINGS.get(self.key, "")


def plate_title(key: str, goal: str) -> str:
    """A plate and condition as players name it in English ("Shin Kiwami"); "" for a plate with no kanji yet.

    :param key: The plate's key.
    :type key: str
    :param goal: The condition's kanji.
    :type goal: str
    :rtype: str
    """
    reading = READINGS.get(key, "")
    return f"{reading} {GOAL_READINGS[goal]}" if reading and goal in GOAL_READINGS else ""


# 真 has no 将, and leaves out the standard ジングルベル; 前前前世 came back as a revival and the wiki
# says it counts for no 制覇 plate, which makes it one of 菫 and 舞. 舞 is every standard chart up to
# FiNALE with Re:MASTER, and is the one plate with a clear condition.
_ZENZENZENSE = frozenset({("前前前世", "std")})
PLATES: Tuple[Plate, ...] = (
    Plate("真", ("100", "110"), ("極", "神", "舞舞"), excluded=frozenset({("ジングルベル", "std")})),
    *[Plate(kanji or name, (code,), ("極", "将", "神", "舞舞"), excluded=_ZENZENZENSE if code == "185" else frozenset())
      for code, name, kanji in VERSIONS if code not in ("100", "110")],
    Plate("舞", tuple(code for code, _n, _k in VERSIONS if code < "200"), ("覇者", "極", "将", "神", "舞舞"),
          std_only=True, remaster=True, excluded=_ZENZENZENSE),
)
PLATE_KEYS = {plate.key: plate for plate in PLATES}


def version_code(name: Any) -> str:
    """The otoge-db code for a version as dxrating or the site names it; "" for one it does not know.

    :param name: The version's name, such as ``"FESTiVAL PLUS"``.
    :type name: Any
    :rtype: str
    """
    text = str(name or "").strip()
    return _OTHER_NAMES.get(text) or next((code for code, known, _k in VERSIONS if known == text), "")


def meets(goal: str, accuracy: float, fc: str, fs: str) -> bool:
    """Whether one score satisfies a plate condition.

    :param goal: ``"覇者"``, ``"極"``, ``"将"``, ``"神"`` or ``"舞舞"``.
    :type goal: str
    :param accuracy: The achievement, as a percentage.
    :type accuracy: float
    :param fc: The combo lamp as maimai DX NET writes it (``"FC+"``).
    :type fc: str
    :param fs: The sync lamp (``"FDX"``).
    :type fs: str
    :rtype: bool
    """
    fc, fs = str(fc or "").upper(), str(fs or "").upper()
    if goal == "覇者":
        return accuracy >= 80.0
    if goal == "将":
        return accuracy >= 100.0
    if goal == "極":
        return fc in _FC
    if goal == "神":
        return fc in _AP
    if goal == "舞舞":
        return fs in _FDX
    return False


def shortfall(goal: str, score: Optional[Any]) -> str:
    """What a chart still lacks for a condition, in a few words: "99.81% → SSS", "FC+ → AP", "unplayed".

    :param goal: The plate condition.
    :type goal: str
    :param score: The player's score on the chart, or None when it is unplayed.
    :type score: Optional[Any]
    :rtype: str
    """
    if score is None:
        return "unplayed"
    if goal in ("覇者", "将"):
        return f"{float(score.accuracy or 0):.2f}% → {GOAL_LABELS[goal]}"
    lamp = str((score.fs_status if goal == "舞舞" else score.fc_status) or "").upper()
    if lamp in ("", "NONE", "SYNC"):
        return f"no {GOAL_LABELS[goal]}"
    return f"{lamp} → {GOAL_LABELS[goal]}"


def _in_game(index: ChartIndex, chart: ChartRef) -> bool:
    # the plates count what the player's cabinet has: nothing removed, nothing another region keeps to itself
    if not index.playable(chart):
        return False
    letter = {"jp": "j", "cn": "c"}.get(index.region or "")
    return not letter or letter in chart.regions


def _counts(plate: Plate, chart: ChartRef) -> bool:
    if chart.edition not in plate.versions:
        return False
    if chart.difficulty == "remaster" and not plate.remaster:
        return False
    if plate.std_only and chart.chart_type != "std":
        return False
    return (chart.title, chart.chart_type) not in plate.excluded


def _best_scores(songs: Iterable[Any], index: ChartIndex) -> Dict[int, Any]:
    """The player's score on each chart the index knows, keyed by the chart's identity.

    :param songs: The player's scores.
    :type songs: Iterable[Any]
    :param index: The chart database.
    :type index: ChartIndex
    :rtype: Dict[int, Any]
    """
    best: Dict[int, Any] = {}
    for song in songs:
        difficulty = str(song.difficulty_type or "").lower()
        if difficulty not in DIFFICULTY_ORDER:
            continue          # utage has no plate
        chart = index.get((str(song.name), str(song.chart_type or "std").lower(), difficulty), getattr(song, "level", None))
        if chart is None:
            continue
        held = best.get(id(chart))
        if held is None or float(song.accuracy or 0) > float(held.accuracy or 0):
            best[id(chart)] = song
    return best


def _required(index: ChartIndex, plate: Plate) -> List[ChartRef]:
    return [chart for chart in index.values() if _counts(plate, chart) and _in_game(index, chart)]


def plate_overview(songs: Iterable[Any], index: ChartIndex) -> List[Dict[str, Any]]:
    """Every plate with how many charts it asks for and how many of them already meet each condition.

    :param songs: The player's scores (``analyzer.songs``).
    :type songs: Iterable[Any]
    :param index: The player's chart database, which knows their region.
    :type index: ChartIndex
    :returns: One entry per plate, oldest version first and 舞 last.
    :rtype: List[Dict[str, Any]]
    """
    best = _best_scores(songs, index)
    charts = [chart for chart in index.values() if _in_game(index, chart)]
    out = []
    for plate in PLATES:
        required = [chart for chart in charts if _counts(plate, chart)]
        played = [best[id(chart)] for chart in required if id(chart) in best]
        goals = [{"goal": goal, "label": GOAL_LABELS[goal], "title": plate_title(plate.key, goal), "required": len(required),
                  "met": sum(1 for score in played if meets(goal, float(score.accuracy or 0), score.fc_status, score.fs_status))}
                 for goal in plate.goals]
        out.append({"key": plate.key, "name": plate.name, "reading": plate.reading, "hue": HUES.get(plate.key), "required": len(required),
                    "played": len(played), "goals": goals})
    return out


def plate_standing(plates: Iterable[Dict[str, Any]]) -> Tuple[int, Optional[Tuple[Dict[str, Any], Dict[str, Any]]]]:
    """How many plates are earned, and the unfinished (plate, condition) with the fewest charts left.

    :param plates: The plates as ``plate_overview`` describes them.
    :type plates: Iterable[Dict[str, Any]]
    :rtype: Tuple[int, Optional[Tuple[Dict[str, Any], Dict[str, Any]]]]
    """
    pairs = [(plate, goal) for plate in plates for goal in plate["goals"] if goal["required"]]
    earned = sum(1 for _plate, goal in pairs if goal["met"] >= goal["required"])
    open_pairs = [pair for pair in pairs if pair[1]["met"] < pair[1]["required"]]
    return earned, min(open_pairs, key=lambda pair: pair[1]["required"] - pair[1]["met"], default=None)


def _order(chart: ChartRef, score: Optional[Any]) -> Tuple:
    # the nearest first: charts already played, best score first, then the unplayed from the lowest constant up
    if score is not None:
        return (0, -float(score.accuracy or 0), chart.constant)
    return (1, chart.constant, DIFFICULTY_ORDER.index(chart.difficulty), chart.title.casefold())


# shortcut: a lamp's odds read off one curve per lamp, P(lamp | score) as a normal CDF, centred where this player's own scores
# turn into that lamp (pulled toward a starting guess while they hold few of them) and widened by the score model's spread.
# FDX is sync play, so it borrows the AP curve for the player's half of it. Upgrade if judgements per chart are ever kept.
LAMP_CURVES = {"極": (100.0, 0.45), "神": (100.65, 0.15), "舞舞": (100.65, 0.15)}
_SCORE_GOALS = {"覇者": 80.0, "将": 100.0}
ORDERS = ("likely", "unlikely")


def lamp_centre(songs: Iterable[Any], goal: str) -> float:
    """The score at which half of this player's runs carry the lamp, from their own scores, pulled toward the starting guess.

    :param songs: The player's scores.
    :type songs: Iterable[Any]
    :param goal: ``"極"``, ``"神"`` or ``"舞舞"``.
    :type goal: str
    :rtype: float
    """
    guess, spread = LAMP_CURVES[goal]
    lamp = "神" if goal == "舞舞" else goal
    runs = [(float(s.accuracy or 0), meets(lamp, float(s.accuracy or 0), s.fc_status, s.fs_status))
            for s in songs if float(s.accuracy or 0) >= 97.0]
    held = sum(1 for _a, has in runs if has)
    weight = min(held, len(runs) - held)
    if not weight:
        return guess

    def fit(centre: float) -> float:
        total = 0.0
        for accuracy, has in runs:
            p = min(1 - 1e-6, max(1e-6, _normal_cdf((accuracy - centre) / spread)))
            total += math.log(p if has else 1 - p)
        return total
    best = max((98.0 + step * 0.05 for step in range(61)), key=fit)
    return (weight * best + 8 * guess) / (weight + 8)


def _expect(profile: Any, key: Tuple[str, str, str], constant: float, accuracy: float, played: bool) -> Optional[Tuple[float, float]]:
    """The score the model expects on a chart and its spread; an unplayed chart well under the player's level as a repeat play.

    :rtype: Optional[Tuple[float, float]]
    """
    guess = chart_prediction(profile, key, constant, accuracy, played=played)
    if guess is None:
        return None
    comfort = float(getattr(profile, "comfort_constant", 0) or 0)
    if played or not comfort:
        return guess["expected"], guess["sigma"]
    # shortcut: the first-pass drop and spread were measured on charts near the player's level; a plate is mostly charts far
    # under it, read on sight. They fade out over the four levels under the constant where the player expects SS. Upgrade if a
    # backtest of first passes on easy charts ever exists.
    ease = min(1.0, max(0.0, (comfort - constant) / 4))
    curve = min(ACHIEVEMENT_CAP, profile.expected_for(constant, key[2]))
    return (guess["expected"] * (1 - ease) + curve * ease,
            guess["sigma"] * (1 - ease) + max(0.25, profile.run_sigma_at(constant)) * ease)


def chance(goal: str, expected: float, sigma: float, centre: Optional[float] = None) -> float:
    """The chance a run on a chart meets a plate condition, from what the score model expects there.

    :param goal: The condition's kanji.
    :type goal: str
    :param expected: The score a run is expected to land.
    :type expected: float
    :param sigma: How far runs scatter around it.
    :type sigma: float
    :param centre: For a lamp, where this player's runs turn into it (``lamp_centre``).
    :type centre: Optional[float]
    :rtype: float
    """
    if goal in _SCORE_GOALS:
        return _normal_cdf((expected - _SCORE_GOALS[goal]) / max(sigma, 0.05))
    guess, spread = LAMP_CURVES[goal]
    return _normal_cdf((expected - (guess if centre is None else centre)) / math.hypot(sigma, spread))


def chance_band(p: Optional[float]) -> str:
    """A chance in a word the replies colour by: "likely" at 60% and up, "maybe" from 25%, "long" under that.

    :param p: The chance, 0 to 1, or None without a model.
    :type p: Optional[float]
    :rtype: str
    """
    if p is None:
        return ""
    return "likely" if p >= 0.6 else "maybe" if p >= 0.25 else "long"


def chance_text(p: Optional[float]) -> str:
    """A chance as a percentage that never claims certainty: "<1%", "62%", ">99%".

    :param p: The chance, 0 to 1, or None without a model.
    :type p: Optional[float]
    :rtype: str
    """
    if p is None:
        return ""
    return "<1%" if p < 0.005 else ">99%" if p > 0.995 else f"{round(p * 100)}%"


def plate_missing(songs: Iterable[Any], index: ChartIndex, key: str, goal: str, profile: Any = None,
                  order: str = "likely") -> Optional[Dict[str, Any]]:
    """One plate's charts that do not meet a condition yet, the likeliest first (or last); None for a plate or condition that
    does not exist. Without a play profile there are no odds, and the charts come closest score first.

    :param songs: The player's scores (``analyzer.songs``).
    :type songs: Iterable[Any]
    :param index: The player's chart database.
    :type index: ChartIndex
    :param key: The plate, by its kanji (``"真"``) or its version's name while it has none.
    :type key: str
    :param goal: ``"覇者"``, ``"極"``, ``"将"``, ``"神"`` or ``"舞舞"``.
    :type goal: str
    :param profile: The player's play profile (``analyzer.play_profile``), which the odds come from.
    :type profile: Any
    :param order: ``"likely"`` for the likeliest first, ``"unlikely"`` for the longest shots first.
    :type order: str
    :rtype: Optional[Dict[str, Any]]
    """
    plate = PLATE_KEYS.get(key)
    if plate is None or goal not in plate.goals:
        return None
    songs = list(songs)
    best = _best_scores(songs, index)
    required = _required(index, plate)
    missing = []
    for chart in required:
        score = best.get(id(chart))
        if score is not None and meets(goal, float(score.accuracy or 0), score.fc_status, score.fs_status):
            continue
        missing.append((chart, score))
    missing.sort(key=lambda pair: _order(*pair))
    centre = lamp_centre(songs, goal) if goal in LAMP_CURVES else None
    odds: Dict[int, Optional[float]] = {}
    for chart, score in missing:
        accuracy = float(score.accuracy or 0) if score is not None else 0.0
        chart_id = (str(score.name).casefold(), str(score.chart_type or "std").lower(), str(score.difficulty_type).lower()) if score is not None else chart.key
        guess = _expect(profile, chart_id, chart.constant, accuracy, score is not None)
        odds[id(chart)] = chance(goal, *guess, centre) if guess else None
    if any(p is not None for p in odds.values()):
        # a stable sort, so equal odds keep the closest-score order underneath
        missing.sort(key=lambda pair: -(odds[id(pair[0])] or 0.0) if order != "unlikely" else (odds[id(pair[0])] or 0.0))
    rows = [{
        "title": chart.title, "type": chart.chart_type, "difficulty": chart.difficulty, "level": chart.level,
        "constant": round(chart.constant, 1), "cover": chart.cover, "played": score is not None,
        "accuracy": round(float(score.accuracy or 0), 4) if score is not None else None,
        "fc": str(score.fc_status or "") if score is not None else "", "fs": str(score.fs_status or "") if score is not None else "",
        "need": shortfall(goal, score),
        "chance": None if odds[id(chart)] is None else round(odds[id(chart)], 4), "band": chance_band(odds[id(chart)]),
    } for chart, score in missing]
    return {"key": plate.key, "name": plate.name, "reading": plate.reading, "hue": HUES.get(plate.key), "goal": goal, "label": GOAL_LABELS[goal],
            "title": plate_title(plate.key, goal), "required": len(required), "met": len(required) - len(missing), "missing": rows,
            "order": order if order in ORDERS else "likely", "odds": any(row["chance"] is not None for row in rows)}


def plate_choices() -> List[Tuple[str, str]]:
    """Every plate as (English label, key) for a menu: "Hoshi · UNiVERSE PLUS", or the version's name while it has no kanji.

    :rtype: List[Tuple[str, str]]
    """
    return [(f"{plate.reading} · {plate.name}" if plate.reading else plate.name, plate.key) for plate in PLATES]
