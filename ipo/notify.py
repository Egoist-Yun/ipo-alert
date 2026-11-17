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
        pred = ipo.prediction or {}
        key = f"pre:{ipo.no}"
        not_listed = ipo.first_close is None and (not ipo.listing_date or date.fromisoformat(ipo.listing_date) >= today)
        if key not in sent and pred.get("open_down") and not_listed:
            due.append((key, ipo))
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


def _level_text(level: str | None) -> str:
    return {"strong": " · 강한 하락 경고", "warn": " · 하락 경고"}.get(level, "")


def format_alert(ipo: Ipo, site_url: str) -> dict:
    span = f"{_md(ipo.sub_start)}~{_md(ipo.sub_end)}" if ipo.sub_start and ipo.sub_end else "일정 미정"
    lines = [f"⚠ {s['label']}: {_value_text(s)}" for s in ipo.signals if s["flag"] is True]
    pattern = _pattern_line(ipo.patterns, use_open=False)
    if pattern:
        lines.append(pattern)
    pred = ipo.prediction or {}
    prob = pred.get("prob")
    warn = bool(prob and prob.get("warn"))
    level = ipo.warning or ("warn" if warn else None)
    if level == "strong":
        lines.append("강한 하락 경고: 모델과 과거 하락 패턴이 모두 하락을 가리켜요.")
    if warn:
        lines.append(f"하락 경고: 공모가 아래로 끝날 확률 {prob['p_down'] * 100:.0f}% "
                     f"(경고 기준 {prob['threshold'] * 100:.0f}%)")
    elif prob:
        lines.append(f"공모가 아래로 끝날 확률 {prob['p_down'] * 100:.0f}%")
    parts = []
    for key, label in (("open", "시초가 예상"), ("close", "종가 예상")):
        if pred.get(key):
            parts.append(f"{label} {pred[key]['return'] * 100:+.0f}% (±{pred[key]['mae'] * 100:.0f}%p)")
    if parts:
        lines.append(" · ".join(parts))
    if pred.get("knn"):
        lines.append(f"비슷한 {pred['knn']['n']}개 중 {pred['knn']['down_count']}개 하락")
    if pred.get("conflict"):
        lines.append("가격 예측은 상승이지만, 하락을 미리 잡는 데는 과거에 경고가 가격 예측보다 정확했어요." if level else "신호와 예측이 엇갈려요. 두 가지를 함께 보세요.")
    if ipo.unknown_count:
        lines.append(f"확인 불가 {ipo.unknown_count}개")
    lines.append(DISCLAIMER)
    unknown = f" · 확인 불가 {ipo.unknown_count}개" if ipo.flag_count == 0 and ipo.unknown_count else ""
    return {
        "title": f"{ipo.name} ⚠{ipo.flag_count}개{unknown}{_level_text(level)} · 청약 {span}",
        "message": "\n".join(lines),
        "click": f"{site_url.rstrip('/')}/#{ipo.no}",
    }


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
