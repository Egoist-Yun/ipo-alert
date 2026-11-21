"""Push through Firebase Cloud Messaging (HTTP v1). Nothing here logs the token, the service account or the access token."""
import sys

import requests

SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
CHANNEL_ID = "ipo-alerts"
_FCM_ERROR = "type.googleapis.com/google.firebase.fcm.v1.FcmError"
_BAD_REQUEST = "type.googleapis.com/google.rpc.BadRequest"
TOKEN_REFRESH_TIMEOUT = 15  # google-auth waits 120 s by default; a stuck token request must not block every send
_credentials: dict = {}  # service account e-mail -> google credentials, reused inside one process


class InvalidToken(Exception):
    """FCM says the device token is gone or malformed: it has to be replaced by hand (GitHub secret FCM_TOKEN)."""


def fcm_message(payload: dict, token: str) -> dict:
    return {"message": {
        "token": token,
        "notification": {"title": payload["title"], "body": payload["message"][:1000]},
        "data": {"url": payload.get("click", "")},
        "android": {"priority": "high", "notification": {"channel_id": CHANNEL_ID}},
    }}


def _access_token(sa_info: dict) -> str:
    from google.auth.transport.requests import Request
    from google.oauth2 import service_account
    key = sa_info.get("client_email", "")
    creds = _credentials.get(key)
    if creds is None:
        creds = service_account.Credentials.from_service_account_info(sa_info, scopes=[SCOPE])
        _credentials[key] = creds
    if not creds.valid:
        req = Request()
        creds.refresh(lambda *a, **k: req(*a, **{**k, "timeout": TOKEN_REFRESH_TIMEOUT}))
    return creds.token


def _error_info(resp) -> tuple[str, str, bool]:
    """(status, FCM errorCode, token is dead) from an FCM v1 error body. Only an FcmError UNREGISTERED or a BadRequest
    violation on the token field means the device token is bad; a bare 404 / INVALID_ARGUMENT can be a wrong project id or payload."""
    try:
        err = resp.json().get("error") or {}
        status = str(err.get("status") or "")
        error_code, dead = "", False
        for d in err.get("details") or []:
            kind = d.get("@type")
            if kind == _FCM_ERROR:
                error_code = str(d.get("errorCode") or "")
                dead = dead or error_code == "UNREGISTERED"
            elif kind == _BAD_REQUEST:
                dead = dead or any("token" in str(v.get("field") or "") for v in d.get("fieldViolations") or [])
        return status, error_code, dead
    except Exception:
        return "", "", False


def fcm_send(payload: dict, token: str, sa_info: dict, post=requests.post, access_token: str | None = None) -> None:
    bearer = access_token or _access_token(sa_info)
    url = f"https://fcm.googleapis.com/v1/projects/{sa_info['project_id']}/messages:send"
    resp = post(url, json=fcm_message(payload, token), headers={"Authorization": f"Bearer {bearer}"}, timeout=10)
    code = resp.status_code
    if code < 400:
        return
    status, error_code, dead = _error_info(resp)
    text = f"FCM {code} {status} {error_code}".strip()
    raise (InvalidToken if dead else RuntimeError)(text)


def main(argv: list[str] | None = None, env=None, post=requests.post) -> int:
    """python -m ipo.push "<title>" "<message>": one alert through the same routes as the collector (for workflow steps)."""
    from ipo.notify import send, target_from_env
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 2:
        print('usage: python -m ipo.push "<title>" "<message>"', file=sys.stderr)
        return 2
    target = target_from_env(env, post=post)
    if not target:
        print("no notification target configured", file=sys.stderr)
        return 0
    try:
        send({"title": args[0], "message": args[1]}, target, post=post)
    except Exception as e:
        print(f"alert failed: {type(e).__name__}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
