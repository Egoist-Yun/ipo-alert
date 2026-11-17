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
    return resp.content.decode("euc-kr", errors="replace")
