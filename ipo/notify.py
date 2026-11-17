import json
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

from ipo.config import DISCLAIMER
from ipo.models import Ipo

NTFY_URL = "https://ntfy.sh"


def _md(day: str | None) -> str | None:
    if not day:
        return None
    d = date.fromisoformat(day)
    return f"{d.month}/{d.day}"


def due_alerts(ipos: list[Ipo], state: dict, now_kst: datetime) -> list[tuple[str, Ipo]]:
    today = now_kst.date()
    sent = set(state.get("sent", []))
    due = []
    for ipo in ipos:
        if ipo.is_spac or ipo.inst_competition is None:
            continue
        if ipo.sub_end and date.fromisoformat(ipo.sub_end) < today:
            continue
        key = f"result:{ipo.no}"
        if key not in sent:
            due.append((key, ipo))
        key = f"eve:{ipo.no}"
        if (key not in sent and ipo.sub_start and now_kst.hour >= 12
                and today == date.fromisoformat(ipo.sub_start) - timedelta(days=1)):
            due.append((key, ipo))
    return due


def _value_text(sig: dict) -> str:
    v, k = sig["value"], sig["key"]
    if v is None:
        return "확인 불가"
    if k == "price_position":
        return f"{v:,}원"
    if k == "inst_competition":
        return f"{v:.0f}대 1"
    if k == "mood":
        return f"{v * 100:.0f}%"
    return f"{v}%"


def format_alert(ipo: Ipo, site_url: str) -> dict:
    span = f"{_md(ipo.sub_start)}~{_md(ipo.sub_end)}" if ipo.sub_start and ipo.sub_end else "일정 미정"
    lines = [f"⚠ {s['label']}: {_value_text(s)}" for s in ipo.signals if s["flag"] is True]
    pred = ipo.prediction or {}
    parts = []
    if pred.get("knn"):
        parts.append(f"비슷한 {pred['knn']['n']}개 중 {pred['knn']['down_count']}개 하락")
    if pred.get("model"):
        m = pred["model"]
        parts.append(f"모델 예측 {m['return'] * 100:+.0f}% (±{m['mae'] * 100:.0f}%p)")
    if parts:
        lines.append(" · ".join(parts))
    if ipo.unknown_count:
        lines.append(f"확인 불가 {ipo.unknown_count}개")
    lines.append(DISCLAIMER)
    unknown = f" · 확인 불가 {ipo.unknown_count}개" if ipo.flag_count == 0 and ipo.unknown_count else ""
    return {
        "title": f"{ipo.name} ⚠{ipo.flag_count}개{unknown} · 청약 {span}",
        "message": "\n".join(lines),
        "click": f"{site_url.rstrip('/')}/#{ipo.no}",
    }


def send(payload: dict, topic: str, post=requests.post) -> None:
    resp = post(NTFY_URL, json={**payload, "topic": topic}, timeout=10)
    if hasattr(resp, "raise_for_status"):
        resp.raise_for_status()


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
