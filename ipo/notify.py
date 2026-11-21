import json
import os
import traceback
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

from ipo.config import DISCLAIMER
from ipo.models import Ipo
from ipo.push import InvalidToken, fcm_send

NTFY_URL = "https://ntfy.sh"


def _md(day: str | None) -> str | None:
    if not day:
        return None
    d = date.fromisoformat(day)
    return f"{d.month}/{d.day}"


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
        if ipo.is_spac or ipo.withdrawn or ipo.inst_competition is None:
            continue
        pred = ipo.prediction or {}
        key = f"pre:{ipo.no}"
        not_listed = ipo.first_close is None and (not ipo.listing_date or date.fromisoformat(ipo.listing_date) >= today)
        if key not in sent and pred.get("open_down") and not_listed:
            due.append((key, ipo))
        if ipo.sub_end and date.fromisoformat(ipo.sub_end) < today:
            continue
        key = f"result:{ipo.no}"
        if key not in sent and (digest_time or _urgent(ipo, today)):
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


def _pattern_line(patterns: list[dict], use_open: bool) -> str | None:
    key = "open_down" if use_open else "close_down"
    where = "시초가 공모가 아래" if use_open else "첫날 공모가 아래"
    risks = [p for p in patterns if p["kind"] == "risk" and p.get(key) is not None]
    if risks:
        top = max(risks, key=lambda p: p[key])
        return f"과거 하락 패턴: {top['label']} (과거 {top['n']}개 중 {top[key] * 100:.0f}%가 {where})"
    safes = [p for p in patterns if p["kind"] == "safe" and p.get(key) is not None]
    if safes:
        top = min(safes, key=lambda p: p[key])
        return f"과거 하락이 드문 패턴: {top['label']} (과거 {top['n']}개 중 {top[key] * 100:.0f}%만 {where})"
    return None


def _verdict(ipo: Ipo) -> tuple[int, str]:
    """(rank, wording): strong warning first, then warning, then the rest. No warning symbol: the words say it."""
    pred = ipo.prediction or {}
    model_warn = bool((pred.get("open_down") or pred.get("prob") or {}).get("warn"))
    if ipo.warning == "strong":
        return 0, "강한 하락 경고"
    if ipo.warning == "warn" or model_warn:
        return 1, "하락 경고"
    if ipo.flag_count > 0:
        return 2, f"경고 없음 (신호 {ipo.flag_count}개)"
    if ipo.unknown_count >= 2:
        return 2, f"경고 없음 (확인 불가 {ipo.unknown_count}개)"
    return 2, "경고 없음"


def format_digest(kind: str, ipos: list[Ipo], site_url: str) -> dict:
    """One summary alert for several stocks (kind: 'result' = demand-forecast results, 'eve' = subscriptions tomorrow)."""
    title = f"수요예측 결과 {len(ipos)}건" if kind == "result" else f"내일 청약 {len(ipos)}건"
    lines = []
    for ipo in sorted(ipos, key=lambda i: (_verdict(i)[0], i.sub_start or "", i.no)):
        span = f"{_md(ipo.sub_start)}~{_md(ipo.sub_end)}" if ipo.sub_start and ipo.sub_end else "일정 미정"
        lines.append(f"{ipo.name} · {_verdict(ipo)[1]} · 청약 {span}")
    lines.append(DISCLAIMER)
    base = site_url.rstrip("/")
    return {"title": title, "message": "\n".join(lines), "click": f"{base}/#{ipos[0].no}" if len(ipos) == 1 else f"{base}/"}


def format_pre_alert(ipo: Ipo, site_url: str) -> dict:
    """After the subscription closes: open-price outlook using the retail competition."""
    pred = ipo.prediction or {}
    od = pred["open_down"]
    lines = [f"시초가 하락 확률 {od['p_down'] * 100:.0f}% (경고 기준 {od['threshold'] * 100:.0f}%)"]
    pattern = _pattern_line(ipo.patterns, use_open=True)
    if pattern:
        lines.append(pattern)
    op = pred.get("open")
    if op:
        lines.append(f"시초가 예상 {op['price']:,}원 ({op['return'] * 100:+.0f}%, ±{op['mae'] * 100:.0f}%p)")
    if ipo.retail_competition is not None:
        lines.append(f"일반청약 경쟁률 {ipo.retail_competition:.0f}대 1")
    if od["warn"]:
        lines.append(f"과거 검증: 하락의 {od['recall'] * 100:.0f}%를 미리 잡았고, 경고의 {od['precision'] * 100:.0f}%가 맞았어요.")
    lines.append(DISCLAIMER)
    return {
        "title": f"{ipo.name} 상장 전 · "
                 f"{'시초가 강한 하락 경고' if ipo.warning == 'strong' else '시초가 하락 경고' if od['warn'] else '시초가 예상'}",
        "message": "\n".join(lines),
        "click": f"{site_url.rstrip('/')}/#{ipo.no}",
    }


@dataclass(frozen=True)
class Target:
    """Where alerts go: FCM push to the app first, ntfy as the fallback. Secrets stay out of repr and logs."""
    topic: str | None = None
    fcm_token: str | None = field(default=None, repr=False)
    fcm_sa: dict | None = field(default=None, repr=False)
    notes: dict = field(default_factory=dict, compare=False, repr=False)   # once-per-run flags

    @property
    def fcm(self) -> bool:
        return bool(self.fcm_token and self.fcm_sa)

    def __bool__(self) -> bool:
        return bool(self.topic or self.fcm)


def _ntfy(payload: dict, topic: str, post) -> None:
    resp = post(NTFY_URL, json={**payload, "topic": topic}, timeout=10)
    if hasattr(resp, "raise_for_status"):
        resp.raise_for_status()


def send(payload: dict, target: Target, post=requests.post) -> None:
    """FCM first; when it fails ntfy takes over (no ntfy topic: the error goes up). A dead device token additionally
    sends one notice per run through ntfy, because nothing else tells the user the pushes stopped reaching the phone."""
    if not target:
        raise RuntimeError("no notification target configured")
    if target.fcm:
        try:
            fcm_send(payload, target.fcm_token, target.fcm_sa)
            return
        except Exception as e:
            print(f"FCM failed: {type(e).__name__}: {e}")   # no traceback: a library error body must not land in a public log
            if not target.topic:
                raise
            _ntfy(payload, target.topic, post)
            if isinstance(e, InvalidToken) and not target.notes.get("token_notice"):
                target.notes["token_notice"] = True
                try:                                          # the alert itself is delivered: a failed notice must not make the caller resend it
                    _ntfy({"title": "앱 알림 토큰이 무효예요",
                           "message": "앱의 실전 성적 화면에서 새 토큰을 복사해 GitHub 비밀값 FCM_TOKEN을 바꿔 주세요"}, target.topic, post)
                except Exception as e2:
                    print(f"token notice failed: {type(e2).__name__}")
            return
    _ntfy(payload, target.topic, post)


def target_from_env(env=None, post=requests.post) -> Target:
    """Target from NTFY_TOPIC, FCM_TOKEN and FCM_SERVICE_ACCOUNT (JSON text). An unreadable service account turns FCM
    off and, when ntfy is set, says so once through ntfy. Values are never printed."""
    env = os.environ if env is None else env
    topic = env.get("NTFY_TOPIC") or None
    token = env.get("FCM_TOKEN") or None
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
                    _ntfy({"title": "공모주 FCM 설정 읽기 실패",
                           "message": "GitHub 비밀값 FCM_SERVICE_ACCOUNT를 읽지 못해 ntfy로만 보내요"}, topic, post)
                except Exception:
                    traceback.print_exc()
    return Target(topic=topic, fcm_token=token, fcm_sa=sa)


def failure_alert(reason: str) -> dict:
    return {"title": "공모주 수집 실패", "message": reason[:300]}


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
