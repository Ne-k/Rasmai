from tools.checks import ROOT, check


def _chart(title, chart_type="std", difficulty="master", edition="100", **extra):
    from rasmai.engine.analysis import ChartRef
    return ChartRef(title=title, chart_type=chart_type, difficulty=difficulty, constant=12.0, level="12", notes=0,
                    genre="", artist="", cover=f"{title}.png", version=int(edition[:2]), edition=edition, **extra)


def _score(title, chart_type="std", difficulty="master", accuracy=0.0, fc="NONE", fs="NONE"):
    from rasmai.storage.models import SongInfo
    return SongInfo(name=title, chart_type=chart_type, difficulty_type=difficulty, accuracy=accuracy, fc_status=fc, fs_status=fs, level="12")


@check("plates count the right charts and read each condition the game's way")
def _plate_rules():
    from rasmai.engine.analysis import ChartIndex
    from rasmai.engine.plates import PLATE_KEYS, plate_missing, plate_overview
    index = ChartIndex()
    for chart in (
        _chart("Old"), _chart("Old", difficulty="remaster"), _chart("Old", "dx", edition="230"),
        _chart("ジングルベル"), _chart("Gone", deleted=True), _chart("Pink", edition="160"),
        _chart("前前前世", edition="185"), _chart("Fest", "dx", edition="230"),
    ):
        index.add(chart)
    songs = [_score("Old", accuracy=100.2, fc="FC+", fs="FS+"), _score("Old", difficulty="remaster", accuracy=79.9),
             _score("Old", "dx", accuracy=99.9, fc="AP", fs="FDX"), _score("Pink", accuracy=100.0, fc="AP+", fs="FDX+")]
    plates = {p["key"]: p for p in plate_overview(songs, index)}
    goals = {key: {g["goal"]: g["met"] for g in p["goals"]} for key, p in plates.items()}
    problems = []
    # 真: the standard chart only (the DX chart came in FESTiVAL), no Re:MASTER, no ジングルベル, nothing deleted
    if plates["真"]["required"] != 1:
        problems.append(f"真 should ask for the one standard MASTER, got {plates['真']['required']}")
    if "将" in goals["真"]:
        problems.append("真 has no 将 plate")
    if goals["真"] != {"極": 1, "神": 0, "舞舞": 0}:
        problems.append(f"FC+ with FS+ is 極 and nothing more: {goals['真']}")
    # a DX chart added later belongs to the version that added it
    if plates["祭"]["required"] != 2 or goals["祭"]["将"] != 0 or goals["祭"]["神"] != 1 or goals["祭"]["舞舞"] != 1:
        problems.append(f"祭 should hold both FESTiVAL DX charts, one AP and FDX at 99.9%: {plates['祭']}")
    if goals["桃"] != {"極": 1, "将": 1, "神": 1, "舞舞": 1}:
        problems.append(f"100.0000% with AP+ and FDX+ meets every condition: {goals['桃']}")
    if plates["菫"]["required"] != 0:
        problems.append("前前前世 counts for no 制覇 plate")
    # 舞: standard charts up to FiNALE with Re:MASTER, ジングルベル in, 前前前世 out
    if plates["舞"]["required"] != 4 or goals["舞"]["覇者"] != 2:
        problems.append(f"舞 should ask for Old, its Re:MASTER, ジングルベル and Pink, two of them cleared: {plates['舞']}")
    missing = plate_missing(songs, index, "舞", "覇者")
    needs = [row["need"] for row in missing["missing"]]
    if needs != ["79.90% → Clear", "unplayed"]:
        problems.append(f"the charts left for 舞覇者 should be the 79.9% then the unplayed one: {needs}")
    if plate_missing(songs, index, "真", "将") is not None or plate_missing(songs, index, "無", "極") is not None:
        problems.append("a plate or condition that does not exist should answer None")
    if set(PLATE_KEYS) & {"", None}:
        problems.append("every plate needs a key")
    return problems


@check("every debug export reads as plates, the same charts asked of everyone")
def _plate_exports():
    import json
    from rasmai.engine.plates import plate_overview
    from rasmai.scraping.scraper import MaimaiRatingAnalyzer
    from rasmai.storage.models import SongInfo
    fields = SongInfo.__dataclass_fields__
    required, problems = {}, []
    for path in sorted((ROOT / "debug").glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if not data.get("songs"):
            continue
        analyzer = MaimaiRatingAnalyzer()
        analyzer.region = data.get("region") or "intl"
        songs = [SongInfo(**{k: v for k, v in row.items() if k in fields}) for row in data["songs"]]
        for plate in plate_overview(songs, analyzer.chart_index):
            required.setdefault((analyzer.region, plate["key"]), set()).add(plate["required"])
            for goal in plate["goals"]:
                if not 0 <= goal["met"] <= goal["required"]:
                    problems.append(f"{path.name}: {plate['key']}{goal['goal']} met {goal['met']} of {goal['required']}")
    for (region, key), counts in sorted(required.items()):
        if len(counts) > 1:
            problems.append(f"{key} asks {region} players for different numbers of charts: {sorted(counts)}")
    return problems[:8]
