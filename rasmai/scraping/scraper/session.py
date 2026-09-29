import base64
import requests
import threading
import time

from rasmai.config import BROWSER_USER_AGENT, REQUESTS_PER_SECOND


class SessionRejected(ValueError):
    """maimai DX NET did not accept the saved sign-in; the player has to link again."""


class RequestPacer:
    """Spaces the requests this process sends to maimai DX NET, across every thread.

    Each user has their own session, but all of them leave from one address; a
    crowd of analyses must not look like one abusive client."""

    def __init__(self, per_second: float):
        self.interval = 1.0 / per_second if per_second > 0 else 0.0
        self._lock = threading.Lock()
        self._next = 0.0

    def wait(self) -> None:
        if not self.interval:
            return
        with self._lock:
            now = time.monotonic()
            start = max(now, self._next)
            self._next = start + self.interval
        if start > now:
            time.sleep(start - now)


PACER = RequestPacer(REQUESTS_PER_SECOND)


class PacedSession(requests.Session):
    """A requests session that waits for its turn before every call."""

    def request(self, method, url, *args, **kwargs):
        PACER.wait()
        return super().request(method, url, *args, **kwargs)


def cookie_jar_to_header(session: requests.Session) -> str:
    return "; ".join(f"{cookie.name}={cookie.value}" for cookie in session.cookies)


def download_image_base64(image_url: str, cookies: str = "") -> str:
    if not image_url:
        return ""

    try:
        headers = {'User-Agent': BROWSER_USER_AGENT}
        if cookies:
            headers['Cookie'] = cookies

        response = requests.get(image_url, headers=headers, timeout=30)
        if response.status_code != 200:
            return ""

        return base64.b64encode(response.content).decode('utf-8')
    except Exception as e:
        print(f"Error downloading image: {e}")
        return ""
