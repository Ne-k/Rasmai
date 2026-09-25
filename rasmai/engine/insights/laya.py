from typing import Any, Dict, Optional, Sequence, Tuple
import importlib.util
import logging
import math
import os
import threading
import time
import warnings

from rasmai.engine.analysis.picks.model import SHORTLIST_READ

logger = logging.getLogger(__name__)

Key = Tuple[str, str, str]

MODEL = os.getenv("RASMAI_LAYA_MODEL", "convaiinnovations/laya")
BATCH = int(os.getenv("RASMAI_LAYA_BATCH", "32"))
# charts asked about in one go, which is the shortlist every reading gets. Raisable from the
# environment because measuring wants a bigger sample than a player ever sees at once.
CAP = int(os.getenv("RASMAI_LAYA_CAP", str(SHORTLIST_READ)))
RECENT_SHOWN = 3         # plays named in the state, newest first
BRIEF = True             # leave out what the recent plays already imply; see describe_player

# How far the model is allowed to move the ranking, fitted in tools/laya_eval.py against 105 plays
# eight accounts actually went and made after the snapshot the ranking was built from.
#
# The fit says: do not listen to it. Inside the shortlist the arithmetic alone places a played
# chart at 0.565, where 0.5 is a coin toss. Every weight tried made that worse, and monotonically:
# 0.25 -> 0.538, 1.0 -> 0.513, 3.0 -> 0.498. Reversing the model's order is no better (-0.25 ->
# 0.562, -3.0 -> 0.516), so its answers are not backwards, they are noise, and any weight at all
# dilutes an ordering that was already carrying signal.
#
# Kept at the gentlest setting measured rather than removed, because the feature is off until
# someone opts into it and this is the least it can cost them. Nothing above 0.25 has been
# measured as anything but harmful, which is what the sweep holds it to.
WEIGHT = 0.25

# How the model's answers become a multiplier. Fitted in tools/laya_eval.py; "rank" wins because
# only the order of the odds carries anything, never the distance between two of them.
MAPPING = os.getenv("RASMAI_LAYA_MAPPING", "rank")

# A chart the model dislikes should come last among the charts worth the same, not disappear:
# multiplied into a ranking, a zero is not an opinion but a deletion, and the model is not
# allowed to delete a chart that the arithmetic says is worth playing.
FLOOR = 0.25
CEILING = 2.0

# One question, answered per chart, as a calibrated probability. It is deliberately about what the
# player *would pick*, not about what they would score: the curve already answers the second one
# far better than any model reading text about it could.
QUESTIONS: Dict[str, Dict[str, Any]] = {
    "pick": {
        "type": "noul",
        "instructions": "Would this player choose to play this chart in their next few credits, "
                        "going by the songs they have been playing and how hard they play?",
    },
}

_agent: Optional[Any] = None
_tried = False
# Two accounts can be analysed at once, and the model is most of a gigabyte: without this they
# both find nothing loaded and both load one. The same lock is held over asking it, because a
# second forward pass started mid-flight buys nothing on a CPU and doubles the memory in use.
_lock = threading.RLock()


def available() -> bool:
    """Whether the package is installed at all. Never imports it: that pulls in torch.

    :rtype: bool
    """
    return importlib.util.find_spec("laya") is not None


def load() -> Optional[Any]:
    """The model, loaded once and kept. ``None`` if it cannot be had, and it is only ever tried once.

    :rtype: Optional[Any]
    """
    global _agent, _tried
    with _lock:
        if _tried:
            return _agent
        _tried = True
        if not available():
            return None
        try:
            import laya
            logger.info(f"loading the decision model from {MODEL}; the first time also downloads it")
            with warnings.catch_warnings():
                # The checkpoint ships one calibration figure outside the range the package will
                # accept, for choice questions with eleven or more options, and it says so loudly
                # every load. Nothing here asks a choice question, so the figure is never reached.
                # Silenced by its own wording rather than by category, and only around the load.
                warnings.filterwarnings("ignore", message=".*invalid temperatures.*", category=RuntimeWarning)
                _agent = laya.load(MODEL)
            _warn_if_our_question_was_clamped(_agent)
            logger.info(f"laya loaded from {MODEL}")
        except Exception as error:
            logger.warning(f"laya could not be loaded, falling back to the arithmetic: {error}")
            _agent = None
        return _agent


def _warn_if_our_question_was_clamped(agent: Any) -> None:
    """Say something only if the calibration this actually uses was the part found wanting.

    The load warning is silenced because it is about a question type nothing here asks. That is
    only true while it stays true, so the one figure this does use is read back and complained
    about properly if a later checkpoint ships it out of range.
    """
    try:
        import laya
        index = laya.QTYPES[QUESTIONS["pick"]["type"]]
        shipped, applied = float(agent.temperature_raw[index]), float(agent.temperature[index])
    except Exception:
        return
    if abs(shipped - applied) > 1e-9:
        logger.warning(f"the checkpoint's calibration for a {QUESTIONS['pick']['type']} question was "
                       f"{shipped} and had to be pulled to {applied}: the odds it gives are no longer "
                       f"calibrated, so what it says about a chart is worth less than it looks")


def describe_player(profile: Any, recent_shown: int = RECENT_SHOWN, brief: bool = BRIEF) -> Dict[str, Any]:
    """The player as the model reads them: what they play, how hard, and what they are good at.

    Kept to the things a reader of text could use. Every number the curve already handles is left
    out, because the ranking multiplies this answer by those numbers anyway.

    Short on purpose. A longer list of recent songs made the model both slower and *vaguer*: at
    ten songs its answers across a shortlist spread by 0.04, at three by 0.13, and the wider
    spread is the one that ranks better. Attention spent on a tenth song title is attention not
    spent on the chart being asked about.

    :param profile: How the player plays, as measured from their scores.
    :type profile: PlayProfile
    :param recent_shown: How many recent plays to name.
    :type recent_shown: int
    :param brief: Leave out everything the recent plays already imply.
    :type brief: bool
    :rtype: Dict[str, Any]
    """
    summary = {}
    try:
        recent = sorted(profile.recent_keys.items(), key=lambda pair: pair[1])[:recent_shown]
        summary["recently_played"] = [f"{title} ({difficulty} {kind.upper()})"
                                      for (title, kind, difficulty), _index in recent]
        summary["plays_around_level"] = round(profile.reach_constant, 1) or 12.0
        if brief:
            return summary
        summary["style"] = "score grinder" if profile.accuracy_focus >= 0.65 else (
            "clear hunter" if profile.accuracy_focus <= 0.35 else "balanced")
        summary["hardest_cleared_well"] = round(profile.hardest_s, 1)
        good = [t.get("label", "") for t in (profile.traits or []) if float(t.get("offset", 0)) > 0][:3]
        weak = [t.get("label", "") for t in (profile.traits or []) if float(t.get("offset", 0)) < 0][:3]
        if good:
            summary["good_at"] = good
        if weak:
            summary["loses_points_on"] = weak
        if profile.chart_type_bias:
            summary["prefers_chart_type"] = max(profile.chart_type_bias, key=profile.chart_type_bias.get).upper()
        if profile.genre_bias:
            summary["favourite_genres"] = [genre for genre, _weight in
                                           sorted(profile.genre_bias.items(), key=lambda p: -p[1])[:3] if genre]
        if profile.new_version_share:
            summary["share_of_plays_on_new_songs"] = round(profile.new_version_share, 2)
    except Exception as error:
        logger.debug(f"laya could not describe the player: {error}")
    return summary


def describe_chart(chart: Dict[str, Any]) -> Dict[str, Any]:
    """One chart as the model reads it: the words about it, not the arithmetic around it.

    :param chart: ``{"title", "artist", "genre", "level", "difficulty", "chart_type", "is_new",
        "traits"}``, where ``traits`` is the ``(dimension, label)`` pairs the tag reader gives.
    :type chart: Dict[str, Any]
    :rtype: Dict[str, Any]
    """
    out = {
        "song": chart.get("title", ""),
        "artist": chart.get("artist", ""),
        "genre": chart.get("genre", ""),
        "level": str(chart.get("level", "")),
        "difficulty": str(chart.get("difficulty", "")),
        "chart_type": str(chart.get("chart_type", "")).upper(),
    }
    # what kind of chart it is, what era it came from and what genre it sits in are already fields
    # of their own above, so letting them back in as tags would spend the room meant for the
    # patterns and crowd the only part of this a chart cannot be recognised without
    from rasmai.engine.insights.tags import NOT_A_SKILL
    skills, charters = [], []
    for dimension, label in chart.get("traits") or []:
        if dimension == "designer":
            charters.append(label)
        elif dimension not in NOT_A_SKILL:
            skills.append(label)
    if skills:
        out["chart_is_known_for"] = skills[:5]
    if charters:
        # the tag is worded for a trait list ("charts by X"), and this is already a field called who by
        out["charted_by"] = charters[0].split("charts by ", 1)[-1]
    if chart.get("is_new"):
        out["from_the_current_version"] = True
    return {key: value for key, value in out.items() if value not in ("", None)}


def pick_odds(profile: Any, charts: Sequence[Dict[str, Any]]) -> Dict[Key, float]:
    """How likely this player is to pick each chart, as a probability between 0 and 1.

    An empty answer means the model could not be reached, and every caller must already work
    without it. Nothing here raises.

    :param profile: How the player plays, as measured from their scores.
    :type profile: PlayProfile
    :param charts: The shortlist, each carrying at least a ``key``.
    :type charts: Sequence[Dict[str, Any]]
    :rtype: Dict[Key, float]
    """
    agent = load()
    if agent is None or not charts:
        return {}
    wanted = list(charts)[:CAP]
    player = describe_player(profile)
    states = [{"player": player, "chart": describe_chart(chart)} for chart in wanted]
    try:
        # said out loud because it is the better part of a minute on a CPU with nothing else to
        # show for itself, and a log that goes quiet there is indistinguishable from a hang
        logger.info(f"asking the decision model about {len(wanted)} charts")
        started = time.monotonic()
        with _lock:
            results = agent.predict_batch(states, QUESTIONS, batch_size=BATCH)
        spent = time.monotonic() - started
        logger.info(f"the decision model answered for {len(wanted)} charts in {spent:.1f}s "
                    f"({1000 * spent / max(1, len(wanted)):.0f}ms each)")
    except Exception as error:
        logger.warning(f"laya could not answer, falling back to the arithmetic: {error}")
        return {}
    odds: Dict[Key, float] = {}
    for chart, result in zip(wanted, results):
        try:
            value = float(result["answers"]["pick"]["noul"])
        except (KeyError, TypeError, ValueError):
            continue
        if math.isfinite(value):
            odds[chart["key"]] = min(1.0, max(0.0, value))
    return odds


def weigh(odds: Dict[Key, float], weight: float = WEIGHT, how: str = MAPPING) -> Dict[Key, float]:
    """The odds turned into the multiplier the ranking already understands.

    The model's answers across one shortlist sit within a few percent of each other, so handing
    over a ratio to their mean would hand over a ratio of almost exactly one and change nothing.
    What carries the signal is the order they come in, so ``rank`` is what is used: the chart it
    liked most is weighted up, the one it liked least down, and the size of the gap between two
    neighbouring probabilities never matters. ``mean`` and ``spread`` are kept because the fitting
    in tools/laya_eval.py compares all three.

    :param odds: What :func:`pick_odds` gave, for every chart being ranked together.
    :type odds: Dict[Key, float]
    :param weight: 0.0 leaves the ranking exactly as it was, and larger is more said.
    :type weight: float
    :param how: ``rank``, ``spread`` or ``mean``.
    :type how: str
    :rtype: Dict[Key, float]
    """
    if not odds or weight <= 0:
        return {}
    values = list(odds.values())
    middle = sum(values) / len(values)
    if how == "rank":
        order = sorted(odds, key=lambda key: odds[key])
        last = max(1, len(order) - 1)
        raw = {key: math.exp(weight * (2.0 * place / last - 1.0)) for place, key in enumerate(order)}
    elif how == "spread":
        spread = (sum((value - middle) ** 2 for value in values) / len(values)) ** 0.5 or 1e-9
        raw = {key: math.exp(weight * (value - middle) / spread) for key, value in odds.items()}
    elif how == "mean":
        if middle <= 0:
            return {}
        raw = {key: 1.0 + weight * (value / middle - 1.0) for key, value in odds.items()}
    else:
        raise ValueError(f"no mapping called {how}")
    return {key: min(CEILING, max(FLOOR, value)) for key, value in raw.items()}


def taste(profile: Any, charts: Sequence[Dict[str, Any]], weight: float = WEIGHT) -> Dict[Key, float]:
    """Ask the model about a shortlist and weigh what it says, in one go.

    :param weight: 0.0 leaves the ranking exactly as it was, and larger is more said.
    :type weight: float
    :rtype: Dict[Key, float]
    """
    return weigh(pick_odds(profile, charts), weight=weight)


def _forget() -> None:
    """Drop the loaded model, so a check can run the load path more than once."""
    global _agent, _tried
    with _lock:
        _agent, _tried = None, False
