
from tools.checks import ROOT, check


@check("chart trait labels carry their English wording")
def _labels():
    from rasmai.scraping.mai_notes import english_label
    cases = {"乱打 (streams)": "streams",
             "slow songs (under 130 BPM)": "slow songs (under 130 BPM)",
             "charts by rioN": "charts by rioN"}
    return [f"english_label({k!r}) is {english_label(k)!r}, expected {v!r}"
            for k, v in cases.items() if english_label(k) != v]


@check("what a play lost per note type adds up to what was missing from 101%")
def _losses():
    from rasmai.engine.losses import note_losses
    tap = {"critical": 95, "perfect": 0, "great": 5, "good": 0, "miss": 0}
    breaks = {"critical": 10, "perfect": 0, "great": 0, "good": 0, "miss": 0}
    # 100 taps + 10 breaks: 150 shares, so one tap is 2/3 of a point and five greats cost one fifth each
    lost = note_losses({"tap": tap, "break": breaks}, 101 - 100 / 150)
    problems = []
    if abs(lost.get("tap", 0) - 100 / 150) > 1e-9 or lost.get("break", 0) > 1e-9:
        problems.append(f"five tap greats among 150 shares: {lost}")
    # a break miss loses its five shares and its slice of the 1% bonus; a break perfect's bonus loss lands on breaks too
    breaks = {"critical": 8, "perfect": 1, "great": 0, "good": 0, "miss": 1}
    lost = note_losses({"tap": {"critical": 100, "perfect": 0, "great": 0, "good": 0, "miss": 0}, "break": breaks}, 101 - (500 / 150 + 0.1) - 0.25)
    if abs(lost.get("break", 0) - (500 / 150 + 0.1 + 0.25)) > 1e-9 or lost.get("tap", 0) > 1e-9:
        problems.append(f"one break miss and one break perfect: {lost}")
    if note_losses({}, 100.0):
        problems.append("no judgements should cost nothing")
    return problems


@check("note types become traits measured against what was at stake on them")
def _judgement_traits():
    from rasmai.engine.judgements import (JUDGEMENT_CONFIRM_PLAYS, JUDGEMENT_LEAN_OFFSET, JUDGEMENT_OFFSET,
                                          judgement_traits)
    clean = {"tap": {"critical": 800, "perfect": 0, "great": 0, "good": 0, "miss": 0},
             "break": {"critical": 40, "perfect": 0, "great": 0, "good": 0, "miss": 0}}

    # 800 taps at one share and 40 breaks at five make 1000 shares, so a share is 0.1%: a dropped
    # break costs five of them plus its slice of the 1% bonus, and a great keeps four fifths of a tap
    BREAK_MISS, TAP_GREAT = 5 * 0.1 + 1.0 / 40, 0.1 / 5

    def play(break_misses=0, tap_greats=0):
        notes = {k: dict(v) for k, v in clean.items()}
        notes["break"]["critical"] -= break_misses
        notes["break"]["miss"] = break_misses
        notes["tap"]["critical"] -= tap_greats
        notes["tap"]["great"] = tap_greats
        # the achievement has to be what those judgements actually cost, or note_losses charges
        # the unexplained remainder to breaks and the test measures its own mistake
        return {"notes": notes, "achievement": 101.0 - break_misses * BREAK_MISS - tap_greats * TAP_GREAT}

    problems = []
    if judgement_traits([play()] * 5):
        problems.append("five plays is too few to name a note type, but traits came back")
    # a player who only ever drops breaks: breaks must read negative and taps positive
    rows = [play(break_misses=2) for _ in range(JUDGEMENT_CONFIRM_PLAYS)]
    traits = {t["label"]: t for t in judgement_traits(rows)}
    if set(traits) != {"tap notes", "break notes"}:
        problems.append(f"expected a trait per note type, got {sorted(traits)}")
        return problems
    if traits["break notes"]["offset"] >= 0:
        problems.append(f"breaks cost every point yet read {traits['break notes']['offset']:+.2f}")
    if traits["tap notes"]["offset"] <= 0:
        problems.append(f"taps were clean yet read {traits['tap notes']['offset']:+.2f}")
    if not traits["break notes"]["verified"]:
        problems.append("25 plays of dropped breaks should be stated, not left as a lean")
    total = sum(t["offset"] for t in traits.values())
    if abs(total) > 0.05:
        problems.append(f"offsets should cancel against the player's own rate, they sum to {total:+.2f}")
    # a break is worth five taps, so losing proportionally to the stake is not a weakness
    even = judgement_traits([play(break_misses=1, tap_greats=100) for _ in range(JUDGEMENT_CONFIRM_PLAYS)])
    if any(t["verified"] or t["leaning"] for t in even):
        problems.append(f"loss spread across the stake should name nobody: {[(t['label'], t['offset']) for t in even]}")
    # a gap too small to state is still a lean; plenty of plays must not make it vanish instead
    # a break dropped on three plays in four, so the gap lands between the two bars rather than on one
    small = judgement_traits([play(break_misses=1 if n % 4 else 0)
                              for n in range(JUDGEMENT_CONFIRM_PLAYS * 2)])
    breaks = next(t for t in small if t["label"] == "break notes")
    if not JUDGEMENT_LEAN_OFFSET <= abs(breaks["offset"]) < JUDGEMENT_OFFSET:
        problems.append(f"expected a gap between the lean and stated bars to test with, got {breaks['offset']:+.2f}")
    elif not breaks["leaning"] or breaks["verified"]:
        problems.append(f"{breaks['offset']:+.2f} over {breaks['count']} plays should lean, not disappear")
    return problems


@check("the judgement profile names the note type carrying more than its share of the loss")
def _judgements():
    from rasmai.engine.judgements import judgement_profile
    clean = {"critical": 100, "perfect": 0, "great": 0, "good": 0, "miss": 0}
    # 900 taps clean, 100 breaks with a miss each play: the breaks are a tenth of the notes and nearly all of the loss
    play = {"notes": {"tap": dict(clean, critical=900), "break": dict(clean, critical=98, miss=2)}, "fast": 3, "late": 9}
    play["achievement"] = 101 - 2 * (5 * 100 / 1400 + 1 / 100)
    problems = []
    if judgement_profile([play, play]) is not None:
        problems.append("two plays should not be enough")
    profile = judgement_profile([play, play, play])
    if not profile or profile["weak"] != "break":
        problems.append(f"breaks should be the weak type: {profile and profile['weak']}")
    if profile and profile["lateShare"] != 0.75:
        problems.append(f"late share should be 0.75: {profile['lateShare']}")
    if profile and abs(profile["lostPerPlay"] - (101 - play["achievement"])) > 1e-3:
        problems.append(f"loss per play should match what the plays lost: {profile['lostPerPlay']}")
    return problems


@check("the permutation test can resolve the threshold it is judged against")
def _trait_confirmation():
    import math
    from rasmai.engine.insights import traits as T

    problems = []
    # a permutation p-value can only land on k/(n+1). If the threshold sits below the second step
    # the gate silently becomes "not one shuffle may beat it", and a trait measured over hundreds
    # of charts gets refused on the luck of a single shuffle rather than on the player's data.
    # This was true at 80 shuffles against p <= 0.02, where 1/81 was the only value that passed.
    for name, threshold in (("TRAIT_P", T.TRAIT_P), ("TRAIT_LEAN_P", T.TRAIT_LEAN_P)):
        room = math.floor(threshold * (T.TRAIT_PERMUTATIONS + 1))
        if room < 4:
            problems.append(f"{name} <= {threshold} over {T.TRAIT_PERMUTATIONS} shuffles lets only {room} of them "
                            f"beat a trait: the test cannot resolve its own threshold")
    if T.TRAIT_CONFIRM_CHARTS < T.TRAIT_MIN_CHARTS:
        problems.append("a trait cannot need fewer charts to be confirmed than to be measured at all")
    if T.TRAIT_LEAN_OFFSET >= T.TRAIT_THRESHOLD:
        problems.append("a leaning trait should be a weaker claim than a confirmed one, not a stronger one")
    if T.TRAIT_LEAN_P < T.TRAIT_P:
        problems.append("a leaning trait should be a weaker claim than a confirmed one, not a rarer one")

    # the note types are judged on plays rather than on shuffled tags, but they end up in the same
    # list, and notable() re-checks every row against TRAIT_THRESHOLD. A note type confirmed under a
    # lower bar than that would pass its own gate, fail notable(), and be excluded from leaning() for
    # being confirmed: shown nowhere at all.
    from rasmai.engine import judgements as J
    if J.JUDGEMENT_OFFSET < T.TRAIT_THRESHOLD:
        problems.append(f"a note type confirmed at {J.JUDGEMENT_OFFSET} would vanish from every list, "
                        f"because a confirmed trait is shown only above {T.TRAIT_THRESHOLD}")
    if J.JUDGEMENT_LEAN_OFFSET > J.JUDGEMENT_OFFSET:
        problems.append("a note type should not need a bigger offset to lean than to be confirmed")
    if J.JUDGEMENT_LEAN_PLAYS > J.JUDGEMENT_CONFIRM_PLAYS:
        problems.append("a note type should not need more plays to lean than to be confirmed")

    # every trait row carries the same keys whichever side it came from, or the pages that read
    # both lists have to know which is which
    rows = J.judgement_traits([{"notes": {k: {"critical": 500, "perfect": 0, "great": 0, "good": 0, "miss": 0}
                                          for k in J.KINDS}, "achievement": 100.0} for _ in range(30)])
    for row in rows:
        missing = {"dimension", "label", "offset", "count", "p", "verified", "leaning"} - set(row)
        if missing:
            problems.append(f"a note-type trait is missing {sorted(missing)}, which the trait lists expect")
        break
    return problems


@check("a trait names a skill or a pattern, never who charted it")
def _traits_are_skills():
    from rasmai.engine.insights import even, leaning, notable
    from rasmai.engine.insights import traits as T
    from rasmai.engine.insights.tags import NOT_A_SKILL

    # one of each kind, all far enough out and confirmed, so only the dimension decides
    def axis(dimension, label, offset=0.9, **rest):
        row = {"dimension": dimension, "label": label, "offset": offset, "count": 40, "p": 0.001,
               "verified": True, "leaning": False}
        row.update(rest)
        return row

    skills = [axis("pattern", "fast rotations"), axis("judgement", "tap notes"), axis("tempo", "very fast songs"),
              axis("density", "dense charts"), axis("slide", "slide-heavy")]
    not_skills = [axis("designer", "charts by someone"), axis("genre", "POPS"), axis("era", "BUDDiES and newer"),
                  axis("type", "DX charts")]
    problems = []
    for name, chosen in (("notable", notable(skills + not_skills)),
                         ("leaning", leaning([dict(a, verified=False, leaning=True) for a in skills + not_skills])),
                         ("even", even([dict(a, verified=False, leaning=False, offset=0.0) for a in skills + not_skills]))):
        named = {row["dimension"] for row in chosen}
        for dimension in sorted(named & NOT_A_SKILL):
            problems.append(f"{name}() offered a {dimension} trait; a trait should name a skill the player can work on")
        if name != "even" and not named:
            problems.append(f"{name}() dropped the skills along with the rest")
    if "designer" not in NOT_A_SKILL:
        problems.append("who charted a song is not a skill and should never be named as a trait")

    # the site builds the leaning and level lists itself rather than taking them from the bot, so it
    # keeps its own copy of this rule. Two copies of one rule is how the designer traits came back.
    import re
    # the rule is spread over the traits package now, so the whole of it is read as one piece and
    # the export keyword taken off, which leaves exactly the text this was written against
    source = "\n".join(sorted(path.read_text(encoding="utf-8")
                              for path in (ROOT / "web" / "components" / "dash" / "traits").iterdir()))
    source = source.replace("export const ", "const ").replace("export function ", "function ")
    found = re.search(r"const NOT_A_SKILL = new Set\(\[([^\]]*)\]\)", source)
    if not found:
        problems.append("the site no longer names the dimensions it refuses to call a trait")
    else:
        theirs = set(re.findall(r'"([a-z]+)"', found.group(1)))
        if theirs != NOT_A_SKILL:
            problems.append(f"the site refuses {sorted(theirs)} where the bot refuses {sorted(NOT_A_SKILL)}")
    # the same goes for the numbers the rule is made of. The site kept showing a lean on nine charts
    # after the bot had stopped, because the bar was raised in one copy of the rule and not the other
    from rasmai.engine.insights.traits import TRAIT_CONFIRM_CHARTS, TRAIT_LEAN_OFFSET
    from rasmai.engine.insights.traits import TRAIT_LEAN_P
    for name, ours in (("CONFIRM_CHARTS", TRAIT_CONFIRM_CHARTS), ("LEAN", TRAIT_LEAN_OFFSET),
                       ("LEAN_P", TRAIT_LEAN_P)):
        found = re.search(rf"const {name} = ([0-9.]+);", source)
        if not found:
            problems.append(f"the site no longer keeps a {name} of its own, so the rule cannot be compared")
        elif abs(float(found.group(1)) - float(ours)) > 1e-9:
            problems.append(f"the site uses {name} of {found.group(1)} where the bot uses {ours}")
    lean = [line for line in source.splitlines() if line.strip().startswith("const isLean =")]
    if not lean:
        problems.append("the site no longer says what it counts as leaning")
    elif "CONFIRM_CHARTS" not in lean[0]:
        problems.append("the site shows a lean however few charts are behind it, where the bot does not")

    # the site fills both sides out to a baseline so the tab answers "what should I work on" either
    # way, and every row it adds still has to carry enough charts to mean anything
    watch = [line for line in source.splitlines() if line.strip().startswith("const isWatch =")]
    if not watch:
        problems.append("the site no longer says what it is willing to show beyond what it can claim")
    else:
        if "CONFIRM_CHARTS" not in watch[0]:
            problems.append("the site would fill its lists with traits on too few charts to mean anything")
        if "verified" not in watch[0] or "isLean" not in watch[0]:
            problems.append("the site would show a confirmed or leaning trait twice, once per tier")
    # and the page says how much of its own leaning list chance alone would produce
    if "byChance" not in source:
        problems.append("the site no longer says how many of its leans are what chance produces")
    if not re.search(r"const BASELINE = [1-9]", source):
        problems.append("the site no longer fills both sides out, so one can be empty while the other is not")
    if "t.verified).length" not in source:
        problems.append("the two sides are levelled without keeping every confirmed trait, which can drop one")

    # the curve spreads its dots inside their own constant so a stack of them reads as a stack; more
    # than half a tenth and a dot would sit under a constant the chart does not have
    curve = (ROOT / "web" / "components" / "dash" / "SkillCurve.tsx").read_text(encoding="utf-8")
    spread = re.search(r"const SPREAD = ([0-9.]+)", curve)
    if not spread:
        problems.append("the curve no longer spreads its dots, so a constant's charts draw as one line")
    elif float(spread.group(1)) >= 0.05:
        problems.append(f"a dot may be nudged {spread.group(1)} from its constant, which is into the next one")

    # Windows' Japanese IME does not compose into an input typed as a search box, so a player typing
    # 乱打 into the trait search got nothing. The boxes are plain text with the role that carries the
    # same meaning, and a new one must not go back to the type that breaks.
    boxes = []
    for name in ("Charts", "Lookup", "PatternBrowser", "Picks"):
        text = (ROOT / "web" / "components" / "dash" / f"{name}.tsx").read_text(encoding="utf-8")
        if 'type="search"' in text:
            boxes.append(name)
        if 'className="search' in text and 'role="searchbox"' not in text:
            problems.append(f"the search box in {name}.tsx no longer says it is one, so it is read as a plain field")
    if boxes:
        problems.append(f"{boxes} type a search box as \"search\", which a Japanese IME will not compose into")

    # every number the site decides a trait with has to be the number the bot decided it with
    import re as _re
    for name, value in (("LEAN", T.TRAIT_LEAN_OFFSET), ("LEAN_P", T.TRAIT_LEAN_P),
                        ("CONFIRM_CHARTS", float(T.TRAIT_CONFIRM_CHARTS))):
        found = _re.search(rf"const {name} = ([0-9.]+);", source)
        if not found:
            problems.append(f"the site no longer says what it uses for {name}")
        elif abs(float(found.group(1)) - float(value)) > 1e-9:
            problems.append(f"the site uses {name}={found.group(1)} where the bot uses {value}")

    # and the lists it builds have to be built from the filtered set, not the raw axes
    defines = [line for line in source.splitlines() if line.strip().startswith("const all =")]
    if not defines:
        problems.append("the site no longer says where its trait lists come from")
    elif "NOT_A_SKILL" not in defines[0]:
        problems.append("the site builds its trait lists from every axis, rule or no rule")
    return problems


@check("a measured trait names what a chart asks for, never what it happens to be short of")
def _bands():
    from rasmai.engine.analysis import ChartRef
    from rasmai.engine.insights.tags import chart_traits
    from rasmai.scraping.mai_notes import note_traits

    problems = []
    # a chart light in every note type asks nothing of the hands for any of them, so it is named for none
    if note_traits({"n": 1000, "t": 940, "h": 20, "s": 20, "u": 10, "b": 10}):
        problems.append(f"a chart light in every note type was still given traits: {note_traits({'n': 1000, 't': 940, 'h': 20, 's': 20, 'u': 10, 'b': 10})}")
    heavy = dict(note_traits({"n": 1000, "t": 700, "h": 40, "s": 200, "u": 30, "b": 30}))
    if heavy.get("slide") != "slide-heavy" or len(heavy) != 1:
        problems.append(f"a slide-heavy chart was read as {heavy}")
    # and a chart in the middle of the game's tempo and note count is in no band at all: a band holding
    # the bulk of the game sits on the player's own average and can never say anything
    middle = [trait for trait in chart_traits(ChartRef(title="middling", chart_type="dx", difficulty="master", constant=13.0,
                                                      level="13", notes=750, genre="", artist="", cover="", version=26, bpm=170.0))
              if trait[0] in ("tempo", "density")]
    if middle:
        problems.append(f"a middle-of-the-road chart landed in a tempo or density band: {middle}")
    return problems


@check("traits read from the charts are searchable by everyone")
def _read_tags_searchable():
    from rasmai.engine import patterns
    from rasmai.engine.analysis import ChartIndex, ChartRef
    from rasmai.engine.insights import chart_tags
    from rasmai.scraping import simai

    index = ChartIndex()
    measured = {}
    for n in range(30):
        ref = ChartRef(title=f"chart {n}", chart_type="dx", difficulty="master", constant=13.0, level="13",
                       notes=700, genre="", artist="", cover="", version=25, bpm=170.0)
        index.add(ref)
        measured["|".join(ref.key)] = {"circles": 0.1 if n % 3 == 0 else 0.0, "lv": 13.0}

    held = simai.cached
    simai.cached = lambda: (measured, {"circles": 0.01})
    patterns._catalogue_memo.clear()
    problems = []
    try:
        spun = index.get(("chart 0", "dx", "master"))
        quiet = index.get(("chart 1", "dx", "master"))

        if "spinning round the ring" not in {tag["label"] for tag in chart_tags(spun)}:
            problems.append("a chart that walks you round the ring was not tagged as one")
        if "spinning round the ring" in {tag["label"] for tag in chart_tags(quiet)}:
            problems.append("a chart that stays put was tagged as walking you round the ring")
        if not any(tag.get("read") for tag in chart_tags(spun)):
            problems.append("a trait read from the chart was not marked as read rather than written by hand")

        # the catalogue, and searching it
        patterns._catalogue_memo.clear()
        if not any(item["label"] == "spinning round the ring" for item in patterns.catalogue(index)):
            problems.append("a trait read from the charts was missing from the list to search")
        patterns._catalogue_memo.clear()
        found = patterns.resolve("spinning round", index)
        if found != "spinning round the ring":
            problems.append(f"searching for the walk round the ring found {found!r}")
        else:
            charts = patterns.charts_with(index, found)
            if len(charts) != 10:
                problems.append(f"ten of the thirty charts walk you round the ring, search returned {len(charts)}")
    finally:
        simai.cached = held
        patterns._catalogue_memo.clear()
    return problems


@check("not hunting critical breaks is not a weakness, but dropping breaks still is")
def _break_bonus():
    from rasmai.engine.judgements import judgement_profile, judgement_traits
    from rasmai.engine.losses import WEIGHTS, note_losses

    kept = {"critical": 1.0, "perfect": 0.5, "great": 0.4, "good": 0.3, "miss": 0.0}

    def play(great=0, good=0, miss=0, criticals=0.35):
        """One play, the same everywhere except on the breaks, scored the way maimai would."""
        notes = {}
        for kind, n in (("tap", 700), ("hold", 40), ("slide", 60), ("touch", 20)):
            g, b, m = round(n * 0.012), round(n * 0.002), round(n * 0.001)
            notes[kind] = {"critical": n - g - b - m, "perfect": 0, "great": g, "good": b, "miss": m}
        breaks = 30
        landed = breaks - great - good - miss
        crit = round(landed * criticals)
        notes["break"] = {"critical": crit, "perfect": landed - crit, "great": great, "good": good, "miss": miss}
        total = sum(WEIGHTS[k] * sum(v.values()) for k, v in notes.items())
        base = 100.0 / total
        lost = sum(row["good"] * 3 * base + row["miss"] * 5 * base if kind == "break"
                   else WEIGHTS[kind] * base * (row["great"] / 5 + row["good"] / 2 + row["miss"])
                   for kind, row in notes.items())
        lost += sum(count * (1 - kept[judged]) / breaks for judged, count in notes["break"].items())
        return {"notes": notes, "achievement": round(101.0 - lost, 4), "fast": 8, "late": 9}

    def breaks_of(rows):
        return next((t["offset"] for t in judgement_traits(rows) if t["label"] == "break notes"), None)

    problems = []
    # every break landed; they are simply perfect rather than critical, which is how the game is
    # played by anyone not chasing the bonus. This must not read as a weakness.
    ordinary = [play() for _ in range(40)]
    offset = breaks_of(ordinary)
    if offset is None:
        problems.append("breaks were not measured at all")
    elif offset < -0.2:
        problems.append(f"landing every break but not as a critical was called a weakness at {offset:+.2f}")
    if judgement_profile(ordinary)["weak"] == "break":
        problems.append("the panel named breaks the worst type for a player who did not drop one")

    # and with no critical at all, which is the same player and a lower score
    none_critical = [play(criticals=0.0) for _ in range(40)]
    offset = breaks_of(none_critical)
    if offset is not None and offset < -0.2:
        problems.append(f"never earning a critical break was called a weakness at {offset:+.2f}")
    profile = judgement_profile(none_critical)
    if profile["bonusPerPlay"] <= 0:
        problems.append("the bonus a critical earns was not reported as its own loss")
    if profile["bonus"] <= 0 or profile["bonusShare"] <= 0:
        problems.append("the bonus was measured at nothing when every break was a plain perfect")

    # dropping breaks is still a weakness, and has to be found
    dropped = [play(great=3, good=2, miss=1) for _ in range(40)]
    offset = breaks_of(dropped)
    if offset is None or offset > -0.4:
        problems.append(f"a player dropping breaks every play was measured at {offset}")
    if judgement_profile(dropped)["weak"] != "break":
        problems.append("the panel did not name breaks for a player dropping them every play")

    # and the bonus is only told apart when it is asked for
    counts = ordinary[0]["notes"]
    together = note_losses(counts, ordinary[0]["achievement"])
    apart = note_losses(counts, ordinary[0]["achievement"], bonus_apart=True)
    if "bonus" in together:
        problems.append("the bonus was split out without being asked for, which changes what callers see")
    if abs(sum(together.values()) - sum(apart.values())) > 1e-6:
        problems.append("splitting the bonus out changed how much the play cost in total")
    if apart.get("break", 0) > together.get("break", 0):
        problems.append("taking the bonus off the breaks made them cost more")
    return problems


@check("every trait belongs to a family, and a family follows the charts behind it")
def _families():
    from rasmai.engine.insights import family_axes, unclaimed
    from rasmai.engine.insights.families import FAMILY_MIN_CHARTS
    from rasmai.engine.judgements import KINDS
    from rasmai.engine.simai import DEMANDS
    from rasmai.scraping.mai_notes import PATTERN_ENGLISH, SHARE_BANDS, pattern_label

    # everything the model can currently name, from the places the names come from
    vocabulary = [{"dimension": "pattern", "label": pattern_label(tag)} for tag in PATTERN_ENGLISH]
    vocabulary += [{"dimension": dimension, "label": label} for _f, dimension, _hi, label in SHARE_BANDS]
    vocabulary += [{"dimension": dimension, "label": label} for _k, dimension, label, _fixed in DEMANDS]
    vocabulary += [{"dimension": "judgement", "label": f"{kind} notes"} for kind in KINDS]
    vocabulary += [{"dimension": "tempo", "label": "slow songs (under 130 BPM)"},
                   {"dimension": "tempo", "label": "very fast (over 210 BPM)"},
                   {"dimension": "density", "label": "light charts (under 620 notes)"},
                   {"dimension": "density", "label": "a lot of notes (890+)"}]
    problems = []
    orphans = unclaimed(vocabulary)
    if orphans:
        problems.append(f"no family takes {len(orphans)} of the traits the model can name: {orphans[:4]}")

    # a family follows the charts behind it, so a tag measured on a handful cannot swing it
    axes = [
        {"dimension": "pattern", "label": "乱打 (streams)", "offset": -1.0, "count": 10, "plays": 2, "verified": False},
        {"dimension": "density", "label": "a lot of notes (890+)", "offset": 0.0, "count": 90, "plays": 30,
         "verified": True},
    ]
    families = {f["key"]: f for f in family_axes(axes)}
    speed = families.get("speed")
    if speed is None:
        problems.append("a family with a hundred charts behind it was not drawn")
    else:
        want = round((-1.0 * 10 + 0.0 * 90) / 100, 2)
        if abs(speed["offset"] - want) > 1e-9:
            problems.append(f"ten charts saying -1.0 and ninety saying 0.0 is {want}, got {speed['offset']}")
        if speed["charts"] != 100 or speed["traits"] != 2:
            problems.append(f"the family should carry both traits and a hundred charts, got {speed['charts']}")
        if len(speed["inside"]) != 2:
            problems.append("a family did not carry the traits underneath it, so it cannot be opened up")
        # the confirmed trait sits at 0.0 and the family leans negative, so nothing confirms that lean
        if speed["verified"]:
            problems.append("a family was called confirmed when nothing under it confirms the way it leans")

    # too little behind it and it is not drawn at all
    thin = family_axes([{"dimension": "pattern", "label": "乱打 (streams)", "offset": -1.0,
                         "count": FAMILY_MIN_CHARTS - 1, "plays": 1, "verified": False}])
    if thin:
        problems.append(f"a family with {FAMILY_MIN_CHARTS - 1} charts behind it was drawn anyway")

    # what a chart is is never a skill, so it never reaches a family
    if family_axes([{"dimension": "genre", "label": "POPS＆アニメ", "offset": -1.0, "count": 200, "plays": 9}]):
        problems.append("a genre was rolled into a family, which is not a thing to practise")

    # what a note type costs is measured against the player's own rate, so the five of them sum to
    # zero: averaged into a family they say nothing at all, and they are counted in plays where the
    # rest are counted in charts. They belong in their own panel, not in a family.
    judged = [{"dimension": "judgement", "label": f"{kind} notes", "offset": off, "count": 50, "plays": 50}
              for kind, off in (("break", -0.86), ("tap", 0.26), ("hold", 0.27), ("slide", 0.27), ("touch", 0.05))]
    if abs(sum(t["offset"] for t in judged)) > 0.02:
        problems.append("these offsets no longer sum to zero, so the reasoning below needs revisiting")
    if family_axes(judged):
        problems.append("what a note type costs was rolled into a family, where its sign cannot survive")
    if unclaimed(judged):
        problems.append(f"note types were reported as having no family, when they are meant to have none: {unclaimed(judged)}")
    return problems


@check("a trait read from the charts can name charts to practise it on")
def _read_traits_practice():
    from rasmai.engine.analysis import ChartIndex, ChartRef, build_play_profile, calculate_rating
    from rasmai.engine.insights.traits import practice_for
    from rasmai.scraping import simai
    from rasmai.storage.models import SongInfo

    index, measured, songs = ChartIndex(), {}, []
    for n in range(40):
        ref = ChartRef(title=f"chart {n}", chart_type="dx", difficulty="master", constant=13.0, level="13",
                       notes=700, genre="", artist="", cover="", version=25, bpm=170.0)
        index.add(ref)
        measured["|".join(ref.key)] = {"circles": 0.1 if n % 2 == 0 else 0.0, "lv": 13.0}
        accuracy = 99.0 if n % 2 else 99.5
        songs.append(SongInfo(name=f"chart {n}", chart_type="dx", difficulty_type="master", accuracy=accuracy,
                              is_new=False, level="13", difficulty=13.0, rating=calculate_rating(13.0, accuracy)))
    held = simai.cached
    simai.cached = lambda: (measured, {"circles": 0.01})
    problems = []
    try:
        profile = build_play_profile(songs, [], index, 26)
        axis = next((a for a in profile.trait_axes if a["label"] == "spinning round the ring"), None)
        if axis is None:
            problems.append("the trait was not measured, so there was nothing to practise")
        else:
            picks = practice_for(axis, index, profile, songs, limit=3)
            if not picks:
                problems.append("a trait read from the charts named no charts to practise it on")
            elif not all("spin" in "".join(str(v) for v in p.values()) or p["title"].startswith("chart") for p in picks):
                problems.append(f"the charts named do not carry the trait: {picks}")
        # a note type measured off the judgement pages is not a property of any chart, so it names none
        judged = {"dimension": "judgement", "label": "break notes", "offset": -1.0, "count": 30}
        if practice_for(judged, index, profile, songs):
            problems.append("charts were named for a trait that is about the hands, not about any chart")
    finally:
        simai.cached = held
    return problems


@check("nothing is shown that cannot be confirmed: not a lean on too few charts, not a family of one")
def _only_what_can_graduate():
    from rasmai.engine.insights.families import FAMILY_MIN_CHARTS, FAMILY_MIN_TRAITS, family_axes
    from rasmai.engine.insights.traits import TRAIT_CONFIRM_CHARTS, leaning

    def axis(label, offset, count, **rest):
        return {"dimension": "pattern", "label": label, "offset": offset, "count": count,
                "plays": 2, "verified": False, "leaning": True, **rest}

    problems = []
    # eight charts is enough to measure a trait, twelve to confirm one. A lean in between can never
    # graduate however much the player plays, so it is not told to them as a weakness.
    thin = axis("fast slides", -0.84, TRAIT_CONFIRM_CHARTS - 1)
    thick = axis("trills", -0.84, TRAIT_CONFIRM_CHARTS)
    shown = [a["label"] for a in leaning([thin, thick])]
    if "fast slides" in shown:
        problems.append(f"a lean on {thin['count']} charts was shown, and it can never be confirmed")
    if "trills" not in shown:
        problems.append("a lean on enough charts to be confirmed one day was not shown")

    # and a family averaging one trait is that trait wearing a family's name, drawn the same size as
    # a family averaging thirteen
    lone = [{"dimension": "pattern", "label": "spinning round the ring", "offset": 0.49,
             "count": FAMILY_MIN_CHARTS * 2, "plays": 9, "verified": False, "leaning": False}]
    if family_axes(lone):
        problems.append("a family was drawn from a single trait")
    pair = lone + [{"dimension": "rotation", "label": "速い回転 (fast rotations)", "offset": -0.2,
                    "count": FAMILY_MIN_CHARTS, "plays": 4, "verified": False, "leaning": False}]
    drawn = family_axes(pair)
    if not any(f["key"] == "rotation" for f in drawn):
        problems.append(f"a family of {FAMILY_MIN_TRAITS} traits over {FAMILY_MIN_CHARTS * 3} charts was not drawn")

    # a family still needs the charts as well as the traits
    small = [dict(a, count=4) for a in pair]
    if family_axes(small):
        problems.append("a family with almost no charts behind it was drawn because it had two traits")
    return problems


@check("a measured trait is named after the technique, not after the kind of chart that carries it")
def _trait_wording():
    from rasmai.engine.simai.features import DEMANDS
    from rasmai.scraping.mai_notes import PATTERN_ENGLISH, SHARE_BANDS

    problems = []
    # "charts with trills" is how the model groups them; "trills" is the thing the player does, and
    # the tab is about the player
    for _key, _dimension, label, _fixed in DEMANDS:
        if label.startswith("charts "):
            problems.append(f"{label!r} names a kind of chart rather than what it asks of the hands")
    for _field, _kind, _high, label in SHARE_BANDS:
        if label.endswith(" charts"):
            problems.append(f"{label!r} names a kind of chart rather than what it asks of the hands")

    # the editors' トリル is shown as "trills" and so is the measure taken off the notation, so a row
    # has to say which it is or the two read as one thing said twice
    measured = {label for _k, _d, label, _f in DEMANDS}
    shared = measured & set(PATTERN_ENGLISH.values())
    site = (ROOT / "web" / "components" / "dash" / "traits" / "panels.tsx").read_text(encoding="utf-8")
    if shared and "t.read" not in site:
        problems.append(f"{sorted(shared)} are worded the same as a community tag and nothing says which is which")
    if shared and '"read"' not in (ROOT / "rasmai" / "web" / "dashboard" / "picks.py").read_text(encoding="utf-8"):
        problems.append("the site is never told which traits were read from the notes")
    return problems


@check("a trait is only named when it replicates on the player's own charts")
def _trait_bars_are_earned():
    import math
    from rasmai.engine import judgements as J
    from rasmai.engine.insights import traits as T

    problems = []
    # Measured over six halvings of eight real accounts: a trait keeps its sign across both halves
    # 73% of the time at 0.2-0.3, 80% at 0.4-0.5 and 85% above 0.5. Below about a fifth of a point
    # there is nothing left to replicate, so a bar under that is naming noise whatever its p says.
    FLOOR = 0.2
    if T.TRAIT_LEAN_OFFSET < FLOOR:
        problems.append(f"a lean at {T.TRAIT_LEAN_OFFSET} is under the {FLOOR} the split-half test can still see")
    if T.TRAIT_THRESHOLD <= T.TRAIT_LEAN_OFFSET:
        problems.append("a confirmed trait has to be a stronger claim than a lean, not an equal one")
    if T.TRAIT_P > T.TRAIT_LEAN_P:
        problems.append("a confirmed trait has to be rarer under shuffling than a lean, not commoner")
    # A lean is judged on replicating rather than on rarity, so this bar is looser than the confirm
    # one on purpose. It stops where the evidence stops: the slice from 0.05 to 0.15 was measured at
    # 87% sign agreement, and nothing above 0.15 has been measured at all.
    MEASURED_TO = 0.15
    if T.TRAIT_LEAN_P > MEASURED_TO:
        problems.append(f"a lean bar of p<={T.TRAIT_LEAN_P} goes past the {MEASURED_TO} anyone has "
                        f"checked replicates; measure that band before opening it")
    room = math.floor(T.TRAIT_LEAN_P * (T.TRAIT_PERMUTATIONS + 1))
    if room < 4:
        problems.append(f"p <= {T.TRAIT_LEAN_P} over {T.TRAIT_PERMUTATIONS} shuffles cannot be resolved")
    if J.JUDGEMENT_OFFSET < T.TRAIT_THRESHOLD:
        problems.append(f"a note type confirmed at {J.JUDGEMENT_OFFSET} would vanish from every list, "
                        f"because a confirmed trait is shown only above {T.TRAIT_THRESHOLD}")
    if J.JUDGEMENT_LEAN_OFFSET > T.TRAIT_LEAN_OFFSET:
        problems.append("a note type should not need a bigger offset to lean than a chart trait does")
    return problems
