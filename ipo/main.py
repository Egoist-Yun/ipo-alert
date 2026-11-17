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
from ipo.notify import (due_alerts, failure_alert, format_alert, format_pre_alert, load_state, mark_sent,
                        save_state,
                        send)
from ipo.predict import _usable, calibrate, coverage_names, evaluate, predict_for, select_features
from ipo.signals import score

CALENDAR_DAYS_BACK = 90
RESELECT_EVERY = 20  # re-run variable selection after this many new listings


def _model_config(data_dir: Path, recent: list, full: list) -> tuple[list[str], dict | None]:
    """Variables (forward selection on recent listings) and warning thresholds (validation window),
    cached in data/model.json and recomputed after RESELECT_EVERY new listings."""
    usable = len(_usable(recent))
    path = data_dir / "model.json"
    saved = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if saved.get("names") and saved.get("calibration") and usable - saved.get("n", 0) < RESELECT_EVERY:
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
        out.append(replace(scored, prediction=pred))
    return sorted(out, key=lambda i: (i.sub_start, i.no))


def run(data_dir: Path, topic: str | None, site_url: str, now_kst: datetime,
        fetch=get_html, post=requests.post) -> int:
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    try:
        ipos = _build(data_dir, now_kst, fetch)
        payload = {"updated_at": now_kst.isoformat(), "disclaimer": config.DISCLAIMER,
                   "ipos": [asdict(i) for i in ipos]}
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
        state = load_state(data_dir / "state.json")
        for key, ipo in due_alerts(ipos, state, now_kst):
            try:
                payload = format_pre_alert(ipo, site_url) if key.startswith("pre:") else format_alert(ipo, site_url)
                send(payload, topic, post=post)
            except Exception:
                traceback.print_exc()
                continue
            mark_sent(state, [(key, ipo)])
            save_state(data_dir / "state.json", state)
        save_state(data_dir / "state.json", state)
    return 0


def main() -> None:
    code = run(Path("data"), os.environ.get("NTFY_TOPIC") or None, os.environ.get("SITE_URL", ""),
               datetime.now(config.KST))
    sys.exit(code)


if __name__ == "__main__":
    main()
