"""Prediction ledger: predictions saved before the result is known, scored later against what happened.
An entry is written once and never changed; only the `result` field is filled after the listing."""
import hashlib
import json
import os
from datetime import date, datetime
from pathlib import Path

from ipo import config
from ipo.models import Ipo
from ipo.patterns import warning_level

MARK_START, MARK_END = "<!-- ledger:start -->", "<!-- ledger:end -->"
LABELS = {"pre": "청약 전 모델 (첫날 종가 기준)", "post": "청약 마감 후 모델 (시초가 기준)"}


def model_id(path: Path) -> str:
    """Short hash of the cached model file (variables + thresholds), so each record names the model that made it."""
    try:
        return hashlib.sha1(Path(path).read_bytes()).hexdigest()[:8]
    except OSError:
        return "unknown"


def load_ledger(path) -> dict:
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def save_ledger(path, ledger: dict) -> None:
    p = Path(path)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(ledger, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    os.replace(tmp, p)


def _too_late(ipo: Ipo, now: datetime) -> bool:
    """From 09:00 KST on the listing day a result may already exist: never record from then on."""
    if ipo.first_close is not None:
        return True
    if not ipo.listing_date:
        return False
    return now >= datetime.fromisoformat(ipo.listing_date).replace(hour=9, tzinfo=config.KST)


def _stamp(now: datetime, model: str) -> dict:
    return {"saved_at": now.isoformat(timespec="seconds"), "model": model}


def _before_subscription(saved_at: datetime, sub_start: str | None) -> bool:
    # The source supplies a date without an opening time. Use midnight KST as the cutoff.
    if not isinstance(sub_start, str) or saved_at.utcoffset() is None:
        return False
    try:
        return saved_at.astimezone(config.KST).date() < date.fromisoformat(sub_start)
    except ValueError:
        return False


def _eligible_pre(record: dict, legacy_sub_start: str | None) -> bool:
    try:
        saved_at = datetime.fromisoformat(record.get("saved_at"))
    except (TypeError, ValueError):
        return False
    return _before_subscription(saved_at, record.get("sub_start", legacy_sub_start))


def record_predictions(ledger: dict, ipos: list[Ipo], now: datetime, model: str) -> int:
    """Add the first pre-subscription and the first post-subscription prediction of each upcoming stock."""
    if now.date().isoformat() < config.LEDGER_START:
        return 0
    added = 0
    for ipo in ipos:
        pred = ipo.prediction
        if ipo.is_spac or ipo.withdrawn or not pred or _too_late(ipo, now):
            continue
        entry = ledger.get(str(ipo.no))
        prob = pred.get("prob")
        if prob and not (entry and "pre" in entry) and _before_subscription(now, ipo.sub_start):
            knn = pred.get("knn")
            rec = {"p_down": prob["p_down"], "warn": bool(prob.get("warn")),
                   "level": warning_level({"prob": prob}, ipo.patterns), "threshold": prob.get("threshold"),
                   "knn": {"n": knn["n"], "down_count": knn["down_count"], "median": knn["median"]} if knn else None,
                   "sub_start": ipo.sub_start, **_stamp(now, model)}
            entry = ledger.setdefault(str(ipo.no), {"no": ipo.no, "name": ipo.name, "listing_date": ipo.listing_date,
                                                     "offer_price": ipo.final_price, "result": None})
            entry["pre"] = rec
            added += 1
        od = pred.get("open_down")
        if od and ipo.retail_competition is not None and not (entry and "post" in entry):
            entry = ledger.setdefault(str(ipo.no), {"no": ipo.no, "name": ipo.name, "listing_date": ipo.listing_date,
                                                     "offer_price": ipo.final_price, "result": None})
            entry["post"] = {"p_down": od["p_down"], "warn": bool(od.get("warn")),
                             "level": warning_level(pred, ipo.patterns), "threshold": od.get("threshold"),
                             **_stamp(now, model)}
            added += 1
    return added


def fill_results(ledger: dict, ipos: list[Ipo], now: datetime) -> int:
    """Once the listing result exists, add the actual returns to the entry (predictions stay as saved)."""
    filled = 0
    for ipo in ipos:
        entry = ledger.get(str(ipo.no))
        if entry and not ipo.withdrawn and entry.get("withdrawn"):
            entry.pop("withdrawn")  # it came back: it counts again
        if entry and ipo.withdrawn and not entry.get("withdrawn"):
            entry["withdrawn"] = ipo.withdrawn  # called off: it will never have a result, so it is no longer "pending"
            continue
        if not entry or entry.get("result") or ipo.first_close is None:
            continue
        offer = entry.get("offer_price") or ipo.final_price
        if not offer:
            continue
        open_r = ipo.open_price / offer - 1 if ipo.open_price else None
        close_r = ipo.first_close / offer - 1
        entry["result"] = {"open_return": open_r, "close_return": close_r,
                           "open_down": None if open_r is None else open_r < 0, "close_down": close_r < 0,
                           "filled_at": now.isoformat(timespec="seconds")}
        filled += 1
    return filled


def summarize(ledger: dict, subscription_starts: dict[str, str] | None = None) -> dict:
    """Score pre records only when their save time is provably before subscription day."""
    subscription_starts = subscription_starts or {}
    out = {"since": config.LEDGER_START}
    for key, target in (("pre", "close_down"), ("post", "open_down")):
        saved = [e for no, e in ledger.items() if key in e and not e.get("withdrawn")
                 and (key != "pre" or _eligible_pre(e[key], subscription_starts.get(no)))]
        done = [e for e in saved if (e.get("result") or {}).get(target) is not None]
        warned = [e for e in done if e[key].get("warn")]
        strong = [e for e in warned if e[key].get("level") == "strong"]
        n_down = sum(1 for e in done if e["result"][target])
        out[key] = {"saved": len(saved), "resolved": len(done), "pending": len(saved) - len(done),
                    "warned": len(warned), "caught": sum(1 for e in warned if e["result"][target]),
                    "strong_warned": len(strong), "strong_caught": sum(1 for e in strong if e["result"][target]),
                    "n_down": n_down, "early": n_down < config.LEDGER_MIN_DOWNS}
    return out


def ledger_markdown(summary: dict) -> str:
    lines = [MARK_START, f"## 실전 성적 ({summary['since']} 이후 상장 전에 저장한 예측)", "",
             "| 모델 | 경고 | 강한 경고 | 하락 포착 | 결과 대기 |", "|---|---|---|---|---|"]
    for key in ("pre", "post"):
        m = summary[key]
        lines.append(f"| {LABELS[key]} | 경고 {m['warned']}개 중 {m['caught']}개 적중 | "
                     f"강한 경고 {m['strong_warned']}개 중 {m['strong_caught']}개 적중 | "
                     f"하락 {m['n_down']}개 중 {m['caught']}개 포착 | {m['pending']}개 |")
    if any(summary[k]["early"] for k in ("pre", "post")):
        lines += ["", f"하락 결과가 {config.LEDGER_MIN_DOWNS}개 미만인 모델은 아직 판단하기 일러요."]
    lines.append(MARK_END)
    return "\n".join(lines) + "\n"


def update_backtest_md(path, md: str) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8") if p.exists() else ""
    if MARK_START in text and MARK_END in text:
        a, b = text.index(MARK_START), text.index(MARK_END) + len(MARK_END)
        text = text[:a] + md.rstrip("\n") + text[b:]
    else:
        text = text.rstrip("\n") + "\n\n" + md if text else md
    p.write_text(text, encoding="utf-8")
