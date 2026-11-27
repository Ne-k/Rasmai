import base64
import re
from functools import lru_cache
from pathlib import Path

TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
# the site's typefaces, so an image reads as the site does on every machine that draws one
FONT_DIR = Path(__file__).resolve().parents[2] / "web" / "app" / "fonts"
# Rasmai's own marks, the ones the bot uploads as emoji: ranks, lamps, difficulties, DX and STD
MARK_DIR = Path(__file__).resolve().parents[2] / "brand" / "emoji" / "png"
FONTS = (("Zen Maru Gothic", 700, "ZenMaruGothic-700"), ("Zen Maru Gothic", 900, "ZenMaruGothic-900"),
         ("Zen Kaku Gothic New", 400, "ZenKakuGothicNew-400"), ("Zen Kaku Gothic New", 700, "ZenKakuGothicNew-700"))

_MARKER = re.compile(r"^<!--\s*@([\w-]+)\s*-->.*$", re.M)


@lru_cache(maxsize=1)
def styleimage() -> str:
    """Every style used by the generated images, from templates/rasmai.css, under the typefaces it names and with Rasmai's marks.

    A rendered page has no address to fetch a font or a picture from, so each file is written into its rule: a typeface into
    its @font-face, a mark into ``.mk-<name>``. A file that is not there is left out; the font stacks then fall through to
    what the machine has, and a mark draws nothing.

    :rtype: str
    """
    faces = "".join(
        f'@font-face {{ font-family: "{family}"; font-weight: {weight}; '
        f'src: url("data:font/woff2;base64,{base64.b64encode(path.read_bytes()).decode()}") format("woff2"); }}\n'
        for family, weight, name in FONTS if (path := FONT_DIR / f"{name}.woff2").is_file())
    marks = "".join(f'.mk-{path.stem} {{ background-image: url("data:image/png;base64,{base64.b64encode(path.read_bytes()).decode()}"); }}\n'
                    for path in sorted(MARK_DIR.glob("*.png")) if not path.stem.startswith("rasmai"))     # the logo is drawn by the stylesheet itself
    return faces + (TEMPLATE_DIR / "rasmai.css").read_text(encoding="utf-8") + marks


@lru_cache(maxsize=1)
def _blocks() -> dict:
    """templates/rasmai.html split on its <!-- @name --> markers.

    :rtype: dict
    """
    parts = _MARKER.split((TEMPLATE_DIR / "rasmai.html").read_text(encoding="utf-8"))
    return {parts[i]: parts[i + 1].strip("\n") for i in range(1, len(parts), 2)}


def template(name: str, /) -> str:
    blocks = _blocks()
    if name not in blocks:
        raise KeyError(f"rasmai.html has no <!-- @{name} --> block")
    return blocks[name]


def render(name: str, /, **values) -> str:
    """One block with its {placeholders} filled in.

    Placeholders are str.format fields, so attribute access and format specs work
    but expressions do not: anything computed is passed in by the caller.

    :rtype: str
    """
    return template(name).format(**values)
