from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Optional, Tuple
import numpy as np

Key = Tuple[str, str, str]

# What it takes to be shown anything. These are about how few people a number may stand on, so
# raising one is always safe and lowering one is a privacy decision.
MIN_COHORT = 20                # players in the cohort before either feature says anything
MIN_ACCOUNT_SCORES = 30        # an account with fewer scored charts adds nothing to anyone's neighbours
MIN_PLAYERS_DIFFICULTY = 12    # players on a chart before its observed difficulty is shown
MIN_SHARED = 30                # charts two players must both have a score on to be compared at all
MIN_NEIGHBOURS = 5             # similar players needed before a pick is made
MIN_CHART_NEIGHBOURS = 4       # of those, how many must have played a chart for it to be picked
MIN_AVERAGE = 5                # players with a score on a chart before its typical score is shown
MIN_JUDGED = 5                 # neighbours with a judgement profile before their averages are shown
# only plays this good go into the judgement comparison, on both sides: someone who is stretching on a chart they fail
# loses ten points a play where a neighbour on comfortable charts loses two, and that says nothing about how they hit
JUDGE_FLOOR = 97.0

# Observed difficulty
TARGET = 99.0                  # a best of at least this counts as having beaten the chart (SS)
RIDGE_TAU = 0.7                # prior spread of one chart's offset, in logit units: thin charts shrink to zero
LIST_Z = 1.0                   # a chart is listed as harder/easier only when its offset is this many standard errors
LIST_MIN_GAP = 0.10            # ... and the beat rate at least this far (ten points) from the expected one
BAND = 0.5                     # a chart is compared with the charts within this many levels of its constant
LIST_LENGTH = 10

# Players like you
RATING_WINDOW = 1500           # rating points either side that a neighbour may be
K_NEIGHBOURS = 12
MAX_DISTANCE = 3.0             # median absolute accuracy gap (percentage points) beyond which a player is not "like you"
SCORES_WELL = 97.0             # what the neighbours' typical score must reach for a chart to be offered
MIN_GAP = 1.0                  # how far the typical score must be above the viewer's own best (or expected score), after shrinking
# a gap resting on few neighbours is shrunk as if this many more had scored exactly what the viewer is expected to: the charts
# with the biggest raw gaps are partly the luckiest medians; in the planted world it helped a little, within the noise
SHRINK = 4
REACH_BELOW = 1.5              # picks sit this far under the viewer's reach constant at most ...
REACH_ABOVE = 0.3              # ... and this far over it
PICKS = 12


@dataclass
class Cohort:
    """Everyone's best score per chart, as plain arrays: row u holds ``vals[indptr[u]:indptr[u+1]]`` on charts ``cols[...]``.

    ``tags`` is an opaque stand-in for each account, only ever used to leave the viewer out of their own neighbours.
    """
    keys: List[Key]
    constants: np.ndarray
    ratings: np.ndarray
    tags: List[bytes]
    indptr: np.ndarray
    cols: np.ndarray
    vals: np.ndarray

    @property
    def players(self) -> int:
        return len(self.ratings)

    def owners(self) -> np.ndarray:
        return np.repeat(np.arange(self.players), np.diff(self.indptr))

    def without(self, tag: bytes) -> "Cohort":
        """The same cohort with one account's row taken out."""
        if tag not in self.tags:
            return self
        keep = np.array([t != tag for t in self.tags])
        sizes = np.diff(self.indptr)
        entries = np.repeat(keep, sizes)
        return Cohort(self.keys, self.constants, self.ratings[keep], [t for t in self.tags if t != tag],
                      np.concatenate(([0], np.cumsum(sizes[keep]))), self.cols[entries], self.vals[entries])


def build_cohort(accounts: Iterable[Tuple[bytes, float, Dict[Key, float]]], constants: Dict[Key, float]) -> Cohort:
    """Pack accounts as ``(tag, rating, {chart: best})`` into arrays, in an order that does not depend on how they arrived.

    The columns are the charts in ``constants``; scores on other charts are dropped, and so are accounts
    left with too few scores to compare. Accounts are consumed one at a time, so a generator keeps memory
    to the arrays.
    """
    keys = sorted(constants)
    column = {key: i for i, key in enumerate(keys)}
    rows = []
    for tag, rating, scores in accounts:
        pairs = sorted((column[key], float(score)) for key, score in scores.items() if key in column and score > 0)
        if rating > 0 and len(pairs) >= MIN_ACCOUNT_SCORES:
            rows.append((float(rating), bytes(tag), np.array([c for c, _v in pairs], dtype=np.int32),
                         np.array([v for _c, v in pairs], dtype=np.float32)))
    rows.sort(key=lambda row: (row[0], row[1]))
    sizes = [len(row[2]) for row in rows]
    return Cohort(
        keys, np.array([constants[key] for key in keys], dtype=np.float64),
        np.array([row[0] for row in rows], dtype=np.float64), [row[1] for row in rows],
        np.concatenate(([0], np.cumsum(sizes))).astype(np.int64),
        np.concatenate([row[2] for row in rows]) if rows else np.zeros(0, dtype=np.int32),
        np.concatenate([row[3] for row in rows]) if rows else np.zeros(0, dtype=np.float32))


def chart_medians(cohort: Cohort) -> Dict[Key, float]:
    """The median best score on each chart that at least ``MIN_AVERAGE`` players have a score on.

    A median and not a mean: it sits beside the neighbours' median, and a few failed attempts drag a mean
    down by most of a point on a typical chart and by over ten on some.
    """
    played, typical = _group_median(cohort.cols, cohort.vals.astype(np.float64), len(cohort.keys))
    return {cohort.keys[i]: float(typical[i]) for i in np.flatnonzero(played >= MIN_AVERAGE)}


def _sigmoid(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(z, -30.0, 30.0)))


@dataclass
class Difficulty:
    """What the fit found, per chart: ``(rate, expected, players, offset, error)``.

    ``rate`` is the share of the players who played it that reached ``TARGET``, ``expected`` the share players of
    their rating reach on charts of the same level, and ``offset`` and ``error`` the shrunk log-odds between the two.
    """
    charts: Dict[Key, Tuple[float, float, int, float, float]]


def lean(rate: float, expected: float, offset: float, error: float) -> str:
    """Whether a chart is clearly harder or easier than charts of its level: the offset is clear of its error and the rates are apart."""
    if abs(offset) < LIST_Z * error or abs(rate - expected) < LIST_MIN_GAP:
        return "same"
    return "harder" if offset < 0 else "easier"


def fit_difficulty(cohort: Cohort) -> Difficulty:
    """How often do the people who played each chart reach ``TARGET`` on it, against how often players of their rating do on charts of its level?

    One logistic curve is fitted over every (player, chart) pair: P(best >= TARGET) from the player's rating
    and a separate base for each half-level of constant (``BAND``), std and dx apart. Each chart then gets an offset on top of
    that, with a ridge prior, so a chart few people have played stays at what its level says.

    The comparison is with charts of the same level on purpose. It first measured how hard a chart was in
    levels, with one slope for the constant, and on real players that gave nonsense: people only play charts
    they can mostly clear, so the clear rate hardly falls as the constant rises, the fitted slope came out at
    0.29 a level where about 1.5 is believable, and every shift was multiplied by four or five. Charts of the
    same level need no slope, and a shift is read as a rate.

    What this measures is how the people who played a chart did on it. People pick charts, and a chart that
    suits its players clears more often than a random player of the same rating would clear it, so some of
    what shows is taste. It is a second opinion on the number, not a replacement.
    """
    if cohort.players == 0 or not len(cohort.cols):
        return Difficulty({})
    rows, cols = cohort.owners(), cohort.cols
    y = (cohort.vals >= TARGET).astype(np.float64)
    r = (cohort.ratings - cohort.ratings.mean())[rows] / 1000.0
    # a chart is compared with others of its type as well as its level: on the real players std charts were cleared
    # a good deal less often than dx charts of the same constant, and without this two thirds of them read as harder
    labelled = np.array([[int(np.floor(c / BAND)), int(key[1] == "dx")] for key, c in zip(cohort.keys, cohort.constants)])
    _unique, band = np.unique(labelled, axis=0, return_inverse=True)
    band = band.reshape(-1)
    bands = int(band.max()) + 1
    x = np.zeros((len(y), bands + 1))
    x[np.arange(len(y)), band[cols]] = 1.0
    x[:, bands] = r
    # a thin band is drawn gently toward the rest; the rating slope is left free
    ridge = np.concatenate([np.full(bands, 1e-2), [1e-6]])
    mean = float(y.mean())
    beta = np.zeros(bands + 1)
    beta[:bands] = float(np.log((mean + 1e-3) / (1.0 - mean + 1e-3)))
    for _ in range(40):
        p = _sigmoid(x @ beta)
        step = np.linalg.solve(x.T @ (x * (p * (1.0 - p))[:, None]) + np.diag(ridge), x.T @ (y - p) - ridge * beta)
        beta += step
        if float(np.abs(step).max()) < 1e-7:
            break
    base = x @ beta
    size = len(cohort.keys)
    count = np.bincount(cols, minlength=size)
    offset = np.zeros(size)
    for _ in range(40):
        p = _sigmoid(base + offset[cols])
        grad = np.bincount(cols, weights=y - p, minlength=size) - offset / RIDGE_TAU ** 2
        info = np.bincount(cols, weights=p * (1.0 - p), minlength=size) + 1.0 / RIDGE_TAU ** 2
        step = grad / info
        offset += step
        if float(np.abs(step).max()) < 1e-6:
            break
    p = _sigmoid(base + offset[cols])
    info = np.bincount(cols, weights=p * (1.0 - p), minlength=size) + 1.0 / RIDGE_TAU ** 2
    seen = np.maximum(count, 1)
    rate = np.bincount(cols, weights=y, minlength=size) / seen
    expected = np.bincount(cols, weights=_sigmoid(base), minlength=size) / seen
    out: Dict[Key, Tuple[float, float, int, float, float]] = {}
    for i, key in enumerate(cohort.keys):
        if count[i] >= MIN_PLAYERS_DIFFICULTY:
            out[key] = (float(rate[i]), float(expected[i]), int(count[i]), float(offset[i]), 1.0 / float(np.sqrt(info[i])))
    return Difficulty(out)


def outliers(found: Difficulty, limit: int = LIST_LENGTH) -> Tuple[List[Key], List[Key]]:
    """The charts clearly harder than their level and clearly easier, each biggest offset first (see ``lean``)."""
    harder: List[Tuple[float, Key]] = []
    easier: List[Tuple[float, Key]] = []
    for key, (rate, expected, _n, offset, error) in found.charts.items():
        which = lean(rate, expected, offset, error)
        if which != "same":
            (harder if which == "harder" else easier).append((-abs(offset), key))
    harder.sort()
    easier.sort()
    return [key for _s, key in harder[:limit]], [key for _s, key in easier[:limit]]


def _group_median(groups: np.ndarray, values: np.ndarray, size: int) -> Tuple[np.ndarray, np.ndarray]:
    """Per group: how many values, and their median (zero for an empty group)."""
    counts = np.bincount(groups, minlength=size)
    order = np.lexsort((values, groups))
    ordered = values[order]
    start = np.concatenate(([0], np.cumsum(counts)[:-1]))
    low = np.minimum(start + np.maximum(counts - 1, 0) // 2, max(len(ordered) - 1, 0))
    high = np.minimum(start + counts // 2, max(len(ordered) - 1, 0))
    median = np.zeros(size)
    if len(ordered):
        median = (ordered[low].astype(np.float64) + ordered[high].astype(np.float64)) / 2.0
    median[counts == 0] = 0.0
    return counts, median


def _neighbours(others: Cohort, dense: np.ndarray, rating: float) -> np.ndarray:
    """Rows of the closest players to a viewer whose scores are ``dense`` (NaN where unplayed), closest first."""
    owners = others.owners()
    near = np.abs(others.ratings - rating) <= RATING_WINDOW
    both = near[owners] & ~np.isnan(dense[others.cols])
    gap = np.abs(others.vals[both].astype(np.float64) - dense[others.cols[both]])
    shared, median = _group_median(owners[both], gap, others.players)
    close = np.flatnonzero((shared >= MIN_SHARED) & (median <= MAX_DISTANCE))
    # closest first; equal gaps go to the closer rating, then to the one with more charts in common
    return close[np.lexsort((close, -shared[close], np.abs(others.ratings[close] - rating), median[close]))][:K_NEIGHBOURS]


@dataclass
class LikeYou:
    """What players like the viewer score well on: how many were drawn on, a reason when there is nothing, and the picks."""
    neighbours: int
    reason: str
    picks: List[Dict[str, object]]
    # the neighbours' opaque tags, for the caller to look their judgement pages up by; they never go further than that
    tags: List[bytes] = field(default_factory=list)


def like_you(cohort: Cohort, own: Dict[Key, float], rating: float, tag: Optional[bytes] = None,
             reach: Optional[float] = None,
             expected: Optional[Callable[[Key, float], Optional[float]]] = None,
             wanted: Optional[Callable[[Key, float], bool]] = None) -> LikeYou:
    """Charts that players with a similar record score well on and the viewer has not, or has scored less on.

    Neighbours are players within ``RATING_WINDOW`` rating points who share at least ``MIN_SHARED`` charts
    with the viewer, closest first by the median absolute gap between their scores on those charts; a
    median, so a few charts one of them never practised do not push them away. A chart is offered when
    enough neighbours have played it and their median best is well clear of what the viewer holds or is
    expected to score, once the gap is shrunk by how few neighbours it rests on (``SHRINK``). That median is among the neighbours who played it, and people play what they
    expect to do well on, so it runs a little high on charts few of them chose.

    ``tag`` leaves the viewer's own row out. ``reach`` is the hardest constant the viewer is expected to
    S, from their analysis; without it the hardest chart they have scored 97 or more on stands in.
    ``expected`` says what they would score on a chart they have not played; without it a straight line
    through their own scores does. ``wanted`` is a last filter on charts (still in the game, and so on).
    """
    keys = cohort.keys
    column = {key: i for i, key in enumerate(keys)}
    mine = {column[key]: float(score) for key, score in own.items() if key in column and score > 0}
    if len(mine) < MIN_SHARED or cohort.players < MIN_COHORT:
        return LikeYou(0, "not_enough_scores" if cohort.players >= MIN_COHORT else "not_enough_players", [])
    others = cohort.without(tag) if tag is not None else cohort
    if others.players < MIN_COHORT - 1:
        return LikeYou(0, "not_enough_players", [])

    dense = np.full(len(keys), np.nan)
    for i, score in mine.items():
        dense[i] = score
    order = _neighbours(others, dense, rating)
    if len(order) < MIN_NEIGHBOURS:
        return LikeYou(len(order), "not_enough_players", [])

    entries = np.concatenate([np.arange(others.indptr[u], others.indptr[u + 1]) for u in order])
    ncols, nvals = others.cols[entries], others.vals[entries].astype(np.float64)
    played, typical = _group_median(ncols, nvals, len(keys))

    if reach is None:
        reached = [others.constants[i] for i, score in mine.items() if score >= 97.0]
        reach = float(max(reached)) if reached else None
    if reach is None:
        return LikeYou(len(order), "not_enough_scores", [])
    if expected is None:
        known = np.array(sorted(mine))
        line = np.polyfit(others.constants[known], np.array([mine[i] for i in known]), 1)

        def expected(key: Key, constant: float) -> Optional[float]:
            return float(min(100.5, np.polyval(line, constant)))

    scored: List[Tuple[float, Key, Dict[str, object]]] = []
    for i in np.flatnonzero(played >= MIN_CHART_NEIGHBOURS):
        key, constant = keys[i], float(others.constants[i])
        if not (reach - REACH_BELOW <= constant <= reach + REACH_ABOVE) or typical[i] < SCORES_WELL:
            continue
        if wanted is not None and not wanted(key, constant):
            continue
        yours = mine.get(int(i))
        baseline = yours if yours is not None else expected(key, constant)
        if baseline is None:
            continue
        gap = (typical[i] - baseline) * float(played[i]) / (float(played[i]) + SHRINK)
        if gap < MIN_GAP:
            continue
        scored.append((-gap, key, {
            "key": key, "constant": constant, "yours": yours, "typical": float(typical[i]), "neighbours": int(played[i])}))
    scored.sort(key=lambda item: (item[0], item[1]))
    return LikeYou(len(order), "", [item[2] for item in scored[:PICKS]], [others.tags[int(u)] for u in order])


def compare_judgements(own: Optional[Dict[str, object]], others: List[Dict[str, object]]) -> Optional[Dict[str, object]]:
    """The viewer's judgement profile beside the middle value of their neighbours', note type by note type.

    Each profile is what ``judgement_profile`` returns for one player, so every player counts once however many
    plays they have. A note type, or the early/late split, is shown only when ``MIN_JUDGED`` neighbours have it.
    """
    if own is None or len(others) < MIN_JUDGED:
        return None

    def middle(values: List[float]) -> Optional[float]:
        return round(float(np.median(values)), 3) if len(values) >= MIN_JUDGED else None

    types = []
    for mine in own["types"]:
        theirs = [t for profile in others for t in profile["types"] if t["kind"] == mine["kind"]]
        per100, clean = middle([t["per100"] for t in theirs]), middle([t["clean"] for t in theirs])
        if per100 is not None and clean is not None:
            types.append({"kind": mine["kind"], "per100": mine["per100"], "clean": mine["clean"], "theirPer100": per100, "theirClean": clean})
    if not types:
        return None
    return {"players": len(others), "plays": own["plays"], "types": types,
            "lostPerPlay": own["lostPerPlay"], "theirLostPerPlay": middle([p["lostPerPlay"] for p in others]),
            "lateShare": own["lateShare"], "theirLateShare": middle([p["lateShare"] for p in others if p["lateShare"] is not None])}
