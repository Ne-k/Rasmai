import re
from functools import lru_cache
from pathlib import Path

TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"

_MARKER = re.compile(r"^<!--\s*@([\w-]+)\s*-->.*$", re.M)


@lru_cache(maxsize=1)
def styleimage() -> str:
    """Every style used by the generated images, from templates/rasmai.css.

    :rtype: str
    """
    return (TEMPLATE_DIR / "rasmai.css").read_text(encoding="utf-8")


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


def render_each(name: str, rows, /) -> str:
    """One copy of a block per mapping in `rows`, joined.

    :rtype: str
    """
    markup = template(name)
    return "".join(markup.format(**row) for row in rows)
