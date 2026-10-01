from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Union
from urllib.parse import urlparse
import logging
import os
import re
import ssl
import tempfile
import threading
import time
import warnings

import certifi
import requests
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.x509.oid import AuthorityInformationAccessOID

from rasmai.config import DATABASE_PATH, MAIMAI_BASE_URLS

logger = logging.getLogger(__name__)

# maimaidx.jp sends its own certificate and leaves out the intermediate that signed it. A browser fetches
# the missing one from the address inside the certificate; Python's requests does not, so every request
# to the Japan site failed verification before a sign-in could be sent. Turning verification off is not an
# option for a page the SEGA ID and password are posted to, so the missing certificate is supplied instead.
MAIMAI_HOSTS = {urlparse(url).hostname for url in MAIMAI_BASE_URLS.values()}

SHIPPED = Path(__file__).with_name("certs")
BUNDLE_DIR = DATABASE_PATH.parent / "ca"

# the only places an intermediate is ever fetched from, and only for the maimai hosts above
ISSUER_HOST_SUFFIXES = (".globalsign.com",)
MAX_CERT_BYTES = 20_000
LEARN_EVERY = 600.0          # seconds between attempts per host, so a site that stays broken is not hammered

_lock = threading.Lock()
_tried: dict = {}


def _pems(path: Path) -> str:
    return path.read_text(encoding="ascii") if path.is_file() else ""


def _shipped() -> List[Path]:
    return sorted(SHIPPED.glob("*.pem"))


def _learned_path() -> Path:
    return BUNDLE_DIR / "learned.pem"


def ca_bundle() -> str:
    """A CA file for maimai hosts: the roots Python trusts, the shipped intermediates and any learned ones.

    Rebuilt whenever one of its parts is newer than the file. Only requests to maimai hosts use it.

    :rtype: str
    """
    with _lock:
        parts = [Path(certifi.where()), *_shipped(), _learned_path()]
        newest = max((p.stat().st_mtime for p in parts if p.is_file()), default=0.0)
        body = "\n".join(_pems(p) for p in parts)
        # the data folder first; if it cannot be written the bundle goes to the temp folder, because a bundle
        # that cannot be saved must not stop every request to maimai
        for folder in (BUNDLE_DIR, Path(tempfile.gettempdir()) / "rasmai-ca"):
            target = folder / "bundle.pem"
            try:
                if not target.is_file() or target.stat().st_mtime < newest:
                    folder.mkdir(parents=True, exist_ok=True)
                    scratch = target.with_suffix(f".{os.getpid()}.tmp")
                    scratch.write_text(body, encoding="ascii")
                    os.replace(scratch, target)
                return str(target)
            except OSError:
                continue
        raise OSError("no folder could hold the CA bundle")


def verify_for(url: str) -> Union[bool, str]:
    """What to pass as ``verify=`` for this address: the maimai bundle for a maimai host, normal verification otherwise.

    :param url: The address about to be requested.
    :type url: str
    :rtype: Union[bool, str]
    """
    return ca_bundle() if urlparse(str(url)).hostname in MAIMAI_HOSTS else True


_PEM_BLOCK = re.compile(rb"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----", re.S)


def _roots() -> List[x509.Certificate]:
    # one at a time: a root with an unusual serial number must cost that root, not the whole list
    roots = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for block in _PEM_BLOCK.findall(Path(certifi.where()).read_bytes()):
            try:
                roots.append(x509.load_pem_x509_certificate(block))
            except ValueError:
                continue
    return roots


def signed_by_a_trusted_root(candidate: x509.Certificate, now: Optional[datetime] = None) -> bool:
    """Whether a certificate is a CA, in date, and directly signed by a root in Python's own trust store.

    This is what lets a fetched intermediate be trusted: the plain-HTTP download proves nothing, so the
    signature does. One level is enough for the issuers in use; anything deeper is refused.

    :param candidate: The certificate that was downloaded.
    :type candidate: x509.Certificate
    :rtype: bool
    """
    now = now or datetime.now(timezone.utc)
    try:
        if not candidate.extensions.get_extension_for_class(x509.BasicConstraints).value.ca:
            return False
    except x509.ExtensionNotFound:
        return False
    if not (candidate.not_valid_before_utc <= now <= candidate.not_valid_after_utc):
        return False
    for root in _roots():
        if root.subject != candidate.issuer:
            continue
        try:
            candidate.verify_directly_issued_by(root)
            return True
        except Exception:
            continue
    return False


def _issuer_url(leaf: x509.Certificate) -> Optional[str]:
    try:
        access = leaf.extensions.get_extension_for_class(x509.AuthorityInformationAccess).value
    except x509.ExtensionNotFound:
        return None
    for description in access:
        if description.access_method == AuthorityInformationAccessOID.CA_ISSUERS:
            url = str(description.access_location.value)
            parts = urlparse(url)
            if parts.scheme in ("http", "https") and (parts.hostname or "").endswith(ISSUER_HOST_SUFFIXES):
                return url
    return None


def learn_missing_intermediate(host: str) -> bool:
    """Fetch the intermediate a maimai host leaves out, when a trusted root vouches for it; True if one was added.

    Used when verification fails with "unable to get local issuer certificate" for a maimai host, which is
    what happens when SEGA renews its certificate under an issuer that is not shipped here yet.

    :param host: A maimai host.
    :type host: str
    :rtype: bool
    """
    if host not in MAIMAI_HOSTS:
        return False
    with _lock:
        if time.monotonic() - _tried.get(host, -LEARN_EVERY) < LEARN_EVERY:
            return False
        _tried[host] = time.monotonic()
    try:
        # no verification on purpose: this only reads which certificate the server presents, and sends nothing
        leaf = x509.load_pem_x509_certificate(ssl.get_server_certificate((host, 443), timeout=15).encode("ascii"))
        url = _issuer_url(leaf)
        if not url:
            logger.warning("%s: its certificate names no usable issuer address", host)
            return False
        raw = requests.get(url, timeout=15, stream=True).raw.read(MAX_CERT_BYTES + 1)
        if not raw or len(raw) > MAX_CERT_BYTES:
            return False
        try:
            candidate = x509.load_der_x509_certificate(raw)
        except ValueError:
            candidate = x509.load_pem_x509_certificate(raw)
        if candidate.subject != leaf.issuer or not signed_by_a_trusted_root(candidate):
            logger.warning("%s: the issuer certificate at %s was not signed by a trusted root; not using it", host, url)
            return False
        pem = candidate.public_bytes(serialization.Encoding.PEM).decode("ascii")
        BUNDLE_DIR.mkdir(parents=True, exist_ok=True)
        path = _learned_path()
        if pem.strip() not in _pems(path):
            with open(path, "a", encoding="ascii") as out:
                out.write(pem)
            logger.info("%s: added the missing intermediate certificate %s", host, candidate.subject.rfc4514_string())
        return True
    except Exception as error:
        logger.warning("%s: could not learn the missing intermediate certificate: %s", host, type(error).__name__)
        return False
