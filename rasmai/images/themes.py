from importlib import import_module
from typing import Any, Callable

IMAGES = "images"       # the beta switch on the site that turns the new look on


def themed(user_id: Any, draw: Callable[..., str]) -> Callable[..., str]:
    """``draw`` for an account that switched the new look on, otherwise its classic counterpart, the images as they were.

    A page with no classic version (the plates) is drawn new for everyone.

    :param user_id: Whose image it is, as the Discord user id; None draws the classic one.
    :type user_id: Any
    :param draw: The new look's function, as the builders import it.
    :type draw: Callable[..., str]
    :rtype: Callable[..., str]
    """
    from rasmai.web.dashboard.beta import wants
    if user_id and wants(str(user_id), IMAGES):
        return draw
    try:
        return getattr(import_module(draw.__module__.replace("rasmai.images.", "rasmai.images.classic.", 1)), draw.__name__)
    except (ImportError, AttributeError):
        return draw
