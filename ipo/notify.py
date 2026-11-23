import json
import os
import traceback
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

from ipo.config import APP_NAME
from ipo.models import Ipo
from ipo.push import fcm_send

NTFY_URL = "https://ntfy.sh"
FAILURE_MESSAGE = "앱 정보가 최신이 아닐 수 있어요. 다음 갱신 때 다시 시도해요."


def digest_run(state: dict, now_kst: datetime) -> bool:
    """The morning digest goes out on the first run from 06:00 KST each day (GitHub's schedule can be hours late, so
    "before noon" would lose a whole day). `digest_date` in the state remembers the day it was sent."""
    return now_kst.hour >= 6 and state.get("digest_date") != now_kst.date().isoformat()


def mark_digest(state: dict, now_kst: datetime) -> None:
    state["digest_date"] = now_kst.date().isoformat()


def _urgent(ipo: Ipo, today: date) -> bool:
    """A result that arrives when the subscription starts today or tomorrow cannot wait for the next morning."""
    return bool(ipo.sub_start) and 0 <= (date.fromisoformat(ipo.sub_start) - today).days <= 1


def due_alerts(ipos: list[Ipo], state: dict, now_kst: datetime) -> list[tuple[str, Ipo]]:
    today = now_kst.date()
    sent = set(state.get("sent", []))
    digest_time = digest_run(state, now_kst)
    due = []
    for ipo in ipos:
        if ipo.is_spac or ipo.withdrawn:
            continue
        has_result = ipo.inst_competition is not None   # the eve alert does not wait for the demand-forecast result
        pred = ipo.prediction or {}
        key = f"pre:{ipo.no}"
        not_listed = ipo.first_close is None and (not ipo.listing_date or date.fromisoformat(ipo.listing_date) >= today)
        if key not in sent and has_result and pred.get("open_down") and not_listed:
            due.append((key, ipo))
        if ipo.sub_end and date.fromisoformat(ipo.sub_end) < today:
            continue
        key = f"result:{ipo.no}"
        if key not in sent and has_result and (digest_time or _urgent(ipo, today)):
            due.append((key, ipo))
        key = f"eve:{ipo.no}"
        if (key not in sent and ipo.sub_start and now_kst.hour >= 12
                and today == date.fromisoformat(ipo.sub_start) - timedelta(days=1)):
            due.append((key, ipo))
    return due


def group_alerts(due: list[tuple[str, Ipo]]) -> dict[str, list[tuple[str, Ipo]]]:
    """Split the due alerts by kind: result and eve are sent as one digest each, pre alerts one by one."""
    groups = {"result": [], "eve": [], "pre": []}
    for key, ipo in due:
        groups[key.split(":", 1)[0]].append((key, ipo))
    return groups


def _span(start: str | None, end: str | None) -> str | None:
    """'11/18~19' within a month, '11/28~12/1' across months, a single day once; None when a date is missing."""
    if not start or not end:
        return None
    s, e = date.fromisoformat(start), date.fromisoformat(end)
    if s == e:
        return f"{s.month}/{s.day}"
    return f"{s.month}/{s.day}~{e.day}" if (s.year, s.month) == (e.year, e.month) else f"{s.month}/{s.day}~{e.month}/{e.day}"


def _line(*parts: str | None) -> str:
    return " · ".join(p for p in parts if p)


def _verdict(ipo: Ipo) -> tuple[int, str]:
    """(rank, wording): strong warning first, then warning, then the rest. Wording is empty when there is no warning."""
    if ipo.inst_competition is None:
        return 3, "대기 중"   # nothing to judge yet (also when the page failed to parse): after the stocks with a verdict
    pred = ipo.prediction or {}
    model_warn = bool((pred.get("open_down") or pred.get("prob") or {}).get("warn"))
    if ipo.warning == "strong":
        return 0, "강한 하락 경고"
    if ipo.warning == "warn" or model_warn:
        return 1, "하락 경고"
    return 2, ""


def format_digest(kind: str, ipos: list[Ipo], site_url: str) -> dict:
    """One summary alert for several stocks (kind: 'result' = demand-forecast results, 'eve' = subscriptions tomorrow)."""
    lines = [f"수요예측 결과 {len(ipos)}건" if kind == "result" else f"내일 청약 {len(ipos)}건"]
    for ipo in sorted(ipos, key=lambda i: (_verdict(i)[0], i.sub_start or "", i.no)):
        span = _span(ipo.sub_start, ipo.sub_end) if kind == "result" else None
        lines.append(_line(ipo.name, _verdict(ipo)[1], f"청약 {span}" if span else None))
    base = site_url.rstrip("/")
    return {"title": APP_NAME, "message": "\n".join(lines), "click": f"{base}/#{ipos[0].no}" if len(ipos) == 1 else f"{base}/"}


def format_daily(results: list[Ipo], ipos: list[Ipo], today: date, site_url: str) -> dict:
    """The one alert every day, counts only (the details are in the app): demand-forecast results sent today, stocks whose
    subscription starts today, stocks listing today (SPACs and withdrawn stocks are not counted in the last two)."""
    day = today.isoformat()
    live = [i for i in ipos if not i.is_spac and not i.withdrawn]
    lines = [f"수요예측 : {len(results)}건",
             f"청약 시작 : {sum(1 for i in live if i.sub_start == day)}건",
             f"오늘 상장 : {sum(1 for i in live if i.listing_date == day)}건"]
    return {"title": APP_NAME, "message": chr(10).join(lines), "click": f"{site_url.rstrip('/')}/"}


def format_pre_alert(ipo: Ipo, site_url: str) -> dict:
    """After the subscription closes: the open-price outlook."""
    pred = ipo.prediction or {}
    od = pred["open_down"]
    head = f"{ipo.name} 상장 전"
    if ipo.warning == "strong":
        head += " · 시초가 강한 하락 경고"
    elif od["warn"]:
        head += " · 시초가 하락 경고"
    lines = [head, f"시초가가 공모가 아래일 확률 {od['p_down'] * 100:.0f}%"]
    op = pred.get("open")
    if op:
        lines.append(f"예상 시초가 {op['price']:,}원 ({op['return'] * 100:+.0f}%)")
    return {"title": APP_NAME, "message": "\n".join(lines), "click": f"{site_url.rstrip('/')}/#{ipo.no}"}


@dataclass(frozen=True)
class Target:
    """Where alerts go: FCM push to the app first, ntfy as the fallback. Secrets stay out of repr and logs."""
    topic: str | None = None                                  # the ntfy topic
    fcm_sa: dict | None = field(default=None, repr=False)     # service account: FCM sends to the app's topic with it

    @property
    def fcm(self) -> bool:
        return bool(self.fcm_sa)

    def __bool__(self) -> bool:
        return bool(self.topic or self.fcm)


def _ntfy(payload: dict, topic: str, post) -> None:
    resp = post(NTFY_URL, json={**payload, "topic": topic}, timeout=10)
    if hasattr(resp, "raise_for_status"):
        resp.raise_for_status()


def send(payload: dict, target: Target, post=requests.post) -> None:
    """FCM first; when it fails ntfy takes over (no ntfy topic: the error goes up). Note: a topic send also succeeds when
    nobody is subscribed, so that case never reaches ntfy."""
    if not target:
        raise RuntimeError("no notification target configured")
    if target.fcm:
        try:
            fcm_send(payload, target.fcm_sa)
            return
        except Exception as e:
            print(f"FCM failed: {type(e).__name__}: {e}")   # no traceback: a library error body must not land in a public log
            if not target.topic:
                raise
            _ntfy(payload, target.topic, post)
            return
    _ntfy(payload, target.topic, post)


def target_from_env(env=None, post=requests.post) -> Target:
    """Target from NTFY_TOPIC and FCM_SERVICE_ACCOUNT (JSON text). An unreadable service account turns FCM
    off and, when ntfy is set, says so once through ntfy. Values are never printed."""
    env = os.environ if env is None else env
    topic = env.get("NTFY_TOPIC") or None
    raw = env.get("FCM_SERVICE_ACCOUNT") or None
    sa = None
    if raw:
        try:
            sa = json.loads(raw)
            if not isinstance(sa, dict) or not all(sa.get(k) for k in ("project_id", "client_email", "private_key")):
                raise ValueError("missing fields")
        except Exception as e:
            print(f"FCM_SERVICE_ACCOUNT unreadable ({type(e).__name__}): FCM is off")
            sa = None
            if topic:
                try:
                    _ntfy({"title": APP_NAME,
                           "message": "설정 오류 · FCM_SERVICE_ACCOUNT를 읽지 못해 ntfy로만 보내요"}, topic, post)
                except Exception:
                    traceback.print_exc()
    return Target(topic=topic, fcm_sa=sa)


def failure_alert() -> dict:
    """The run failed: say what it means for the app (the error itself goes to the log, not to the phone)."""
    return {"title": APP_NAME, "message": FAILURE_MESSAGE}


def load_state(path) -> dict:
    p = Path(path)
    if not p.exists():
        return {"sent": []}
    return json.loads(p.read_text(encoding="utf-8"))


def save_state(path, state: dict) -> None:
    Path(path).write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")


def mark_sent(state: dict, alerts: list[tuple[str, Ipo]]) -> None:
    sent = state.setdefault("sent", [])
    for key, _ in alerts:
        if key not in sent:
            sent.append(key)
