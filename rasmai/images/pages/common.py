from typing import Sequence

from rasmai.config import site_label
from rasmai.images.posters import _page


def _image(eyebrow: str, name: str, avatar_b64: str, counters: Sequence[tuple], headline_value: str,
           headline_caption: str, body: str, foot_right: str, body_class: str = "") -> str:
    return _page(eyebrow, name, avatar_b64, counters, headline_value, headline_caption, body,
                 f"Rasmai · {site_label()} · maimai DX · best-50 aware", foot_right, body_class)


def _fc(fc: str, fs: str) -> str:
    bits = [b for b in (str(fc or "").upper(), str(fs or "").upper()) if b and b not in ("NONE", "")]
    return " · ".join(bits)
