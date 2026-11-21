"""Push through Firebase Cloud Messaging (HTTP v1) to the topic every installed app subscribes to (MainActivity).
Nothing here logs the service account or the access token."""
import sys

import requests

SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
CHANNEL_ID = "ipo-alerts"
TOPIC = "ipo-alerts"  # public on purpose: sending to it needs the service account
_FCM_ERROR = "type.googleapis.com/google.firebase.fcm.v1.FcmError"
TOKEN_REFRESH_TIMEOUT = 15  # google-auth waits 120 s by default; a stuck token request must not block every send
_credentials: dict = {}  # service account e-mail -> google credentials, reused inside one process


def fcm_message(payload: dict) -> dict:
    return {"message": {
        "topic": TOPIC,
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


def _error_info(resp) -> tuple[str, str]:
    """(status, FCM errorCode) from an FCM v1 error body; empty strings when the body is not that shape."""
    try:
        err = resp.json().get("error") or {}
        status = str(err.get("status") or "")
        error_code = next((str(d.get("errorCode") or "") for d in err.get("details") or [] if d.get("@type") == _FCM_ERROR), "")
        return status, error_code
    except Exception:
        return "", ""


def fcm_send(payload: dict, sa_info: dict, post=requests.post, access_token: str | None = None) -> None:
    bearer = access_token or _access_token(sa_info)
    url = f"https://fcm.googleapis.com/v1/projects/{sa_info['project_id']}/messages:send"
    resp = post(url, json=fcm_message(payload), headers={"Authorization": f"Bearer {bearer}"}, timeout=10)
    code = resp.status_code
    if code < 400:
        return
    status, error_code = _error_info(resp)
    raise RuntimeError(f"FCM {code} {status} {error_code}".strip())


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
