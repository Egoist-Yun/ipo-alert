import json
import os
import sys
import traceback
from dataclasses import asdict, replace
from datetime import datetime, timedelta
from pathlib import Path

import requests

from ipo import config
from ipo.collect import collect_current, market_mood
from ipo.fetch import get_html
from ipo.history import load_history, save_history, update_history
from ipo.notify import (digest_run, due_alerts, failure_alert, format_digest, format_pre_alert, group_alerts, load_state, mark_digest, mark_sent,
                        save_state,
                        send)
from ipo.patterns import match_patterns, pattern_stats, warning_level
from ipo.predict import _usable, calibrate, coverage_names, evaluate, predict_for, select_features
from ipo.ledger import (fill_results, ledger_markdown, load_ledger, model_id, record_predictions, save_ledger,
                        summarize, update_backtest_md)
from ipo.signals import score

CALENDAR_DAYS_BACK = 90
RESELECT_EVERY = 20  # re-run variable selection after this many new listings


def _model_config(data_dir: Path, recent: list, full: list) -> tuple[list[str], dict | None]:
    """Variables (forward selection on recent listings) and warning thresholds (validation window),
    cached in data/model.json and recomputed after RESELECT_EVERY new listings."""
    usable = len(_usable(recent))
    path = data_dir / "model.json"
    saved = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    complete = "interval" in (saved.get("calibration") or {})  # caches from before counts/intervals are rebuilt
    if saved.get("names") and saved.get("calibration") and complete and usable - saved.get("n", 0) < RESELECT_EVERY:
        return saved["names"], saved["calibration"]
    names = select_features(recent)
    if not names:
        return coverage_names(_usable(recent)), None
    cal = calibrate(full, recent, names)
    _atomic_write(path, json.dumps({"names": names, "n": usable, "calibration": cal}, ensure_ascii=False))
    return names, cal


def _atomic_write(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _build(data_dir: Path, now_kst: datetime, fetch) -> list:
    today = now_kst.date().isoformat()
    history_path = data_dir / "history.json"
    history = load_history(history_path) if history_path.exists() else []
    history = update_history(history, fetch=fetch)
    save_history(history_path, history)

    current = collect_current(fetch=fetch, today=today)
    if not current:
        raise RuntimeError("no IPO rows collected")
    mood = market_mood(history, today)
    recent = [h for h in history if h.listing_date and h.listing_date >= config.RECENT_FROM]
    names, cal = _model_config(data_dir, recent, history)
    ev = evaluate(recent, names)
    post_ev = evaluate(recent, names + ["retail"])
    stats = pattern_stats(history)
    cutoff = (now_kst.date() - timedelta(days=CALENDAR_DAYS_BACK)).isoformat()
    known = {h.no: h for h in history}
    out = []
    for ipo in current:
        past = known.get(ipo.no)
        if past is not None and ipo.first_close is None and past.first_close is not None:
            ipo = replace(ipo, first_close=past.first_close, open_price=past.open_price,
                          listing_date=ipo.listing_date or past.listing_date)
        if not ipo.sub_start or ipo.sub_start < cutoff:
            continue
        scored = score(ipo, mood)
        listed = scored.first_close is not None  # result is known; a prediction would be trained on itself
        pred = None if listed else predict_for(scored, recent, ev, names, calibration=cal,
                                                full_history=history, post_eval=post_ev)
        matched = match_patterns(scored, stats)
        out.append(replace(scored, prediction=pred, patterns=matched, warning=warning_level(pred, matched)))
    return sorted(out, key=lambda i: (i.sub_start, i.no))


def _update_ledger(data_dir: Path, ipos: list, now_kst: datetime) -> dict | None:
    """Save new predictions, fill results, refresh the score. A failure here must never break the calendar."""
    try:
        path = data_dir / "predictions.json"
        ledger = load_ledger(path)
        record_predictions(ledger, ipos, now_kst, model_id(data_dir / "model.json"))
        fill_results(ledger, ipos, now_kst)
        save_ledger(path, ledger)
        summary = summarize(ledger)
        update_backtest_md(data_dir / "backtest.md", ledger_markdown(summary))
        return summary
    except Exception:
        traceback.print_exc()
        return None


def _send_alerts(data_dir: Path, ipos: list, topic: str, site_url: str, now_kst: datetime, post) -> None:
    """Result and eve alerts go out as one digest each, then the pre-listing alerts one by one. A key is remembered (and
    the state saved) only after its send succeeded, so a failed send is tried again on the next run."""
    path = data_dir / "state.json"
    state = load_state(path)
    morning = digest_run(state, now_kst)  # decided before anything is marked
    groups = group_alerts(due_alerts(ipos, state, now_kst))
    for kind in ("result", "eve"):
        items = groups[kind]
        if not items:
            if kind == "result" and morning:
                mark_digest(state, now_kst)     # nothing to send this morning: the afternoon run must not act as a second morning
                save_state(path, state)
            continue
        try:
            send(format_digest(kind, [ipo for _, ipo in items], site_url), topic, post=post)
        except Exception:
            traceback.print_exc()
            continue
        mark_sent(state, items)
        if kind == "result" and morning:
            mark_digest(state, now_kst)  # only a digest that really went out counts as today's
        save_state(path, state)
    for key, ipo in groups["pre"]:
        try:
            send(format_pre_alert(ipo, site_url), topic, post=post)
        except Exception:
            traceback.print_exc()
            continue
        mark_sent(state, [(key, ipo)])
        save_state(path, state)
    save_state(path, state)


def run(data_dir: Path, topic: str | None, site_url: str, now_kst: datetime,
        fetch=get_html, post=requests.post) -> int:
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    try:
        ipos = _build(data_dir, now_kst, fetch)
        payload = {"updated_at": now_kst.isoformat(), "disclaimer": config.DISCLAIMER,
                   "ledger": _update_ledger(data_dir, ipos, now_kst), "ipos": [asdict(i) for i in ipos]}
        _atomic_write(data_dir / "ipos.json", json.dumps(payload, ensure_ascii=False))
    except Exception as e:
        traceback.print_exc()
        if topic:
            try:
                send(failure_alert(f"{type(e).__name__}: {e}"), topic, post=post)
            except Exception:
                traceback.print_exc()
        return 1

    if topic:
        _send_alerts(data_dir, ipos, topic, site_url, now_kst, post)
    return 0


def main() -> None:
    code = run(Path("data"), os.environ.get("NTFY_TOPIC") or None, os.environ.get("SITE_URL", ""),
               datetime.now(config.KST))
    sys.exit(code)


if __name__ == "__main__":
    main()
