import ssl
import time

import requests
from requests.adapters import HTTPAdapter

USER_AGENT = "Mozilla/5.0 (compatible; ipo-alert/1.0)"
MIN_INTERVAL = 1.0


class FetchError(Exception):
    pass


class _LegacyTlsAdapter(HTTPAdapter):
    # www.38.co.kr only completes the TLS handshake with relaxed OpenSSL security level.
    def init_poolmanager(self, *args, **kwargs):
        ctx = ssl.create_default_context()
        ctx.set_ciphers("DEFAULT:@SECLEVEL=0")
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        kwargs["ssl_context"] = ctx
        super().init_poolmanager(*args, **kwargs)


_session = requests.Session()
_session.mount("https://", _LegacyTlsAdapter())
_last_request = 0.0


# 38.co.kr pages are cp949 (a superset of euc-kr: it also has the extended hangul euc-kr lacks). The saved pages decode with 0
# replacement characters, and 900+ real detail pages showed at most 2 (under plain euc-kr), so 20 leaves room for a stray byte while a
# page in the wrong encoding or a binary body (hundreds) fails loudly instead of becoming text full of U+FFFD.
MAX_REPLACEMENT_CHARS = 20


def decode_page(raw: bytes, url: str) -> str:
    text = raw.decode("cp949", errors="replace")
    bad = text.count("�")
    if bad > MAX_REPLACEMENT_CHARS:
        raise FetchError(f"{url}: {bad} undecodable characters (wrong encoding or not a page?)")
    return text


def get_html(url: str) -> str:
    global _last_request
    wait = MIN_INTERVAL - (time.monotonic() - _last_request)
    if wait > 0:
        time.sleep(wait)
    try:
        resp = _session.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
        _last_request = time.monotonic()
        resp.raise_for_status()
    except requests.RequestException as e:
        _last_request = time.monotonic()
        raise FetchError(f"{url}: {e}") from e
    return decode_page(resp.content, url)
