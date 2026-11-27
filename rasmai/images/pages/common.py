from rasmai.images.posters import _page


def _image(eyebrow: str, name: str, avatar_b64: str, headline_value: str,
           headline_caption: str, body: str, foot_right: str, body_class: str = "") -> str:
    return _page(eyebrow, name, avatar_b64, headline_value, headline_caption, body, "", foot_right, body_class)
