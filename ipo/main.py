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
from ipo.notify import (due_alerts, failure_alert, format_alert, load_state, mark_sent, save_state,
                        send)
from ipo.predict import evaluate, predict_for
from ipo.signals import score

CALENDAR_DAYS_BACK = 90


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
    ev = evaluate(history)
    cutoff = (now_kst.date() - timedelta(days=CALENDAR_DAYS_BACK)).isoformat()
    out = []
    for ipo in current:
        if not ipo.sub_start or ipo.sub_start < cutoff:
            continue
        scored = score(ipo, mood)
        out.append(replace(scored, prediction=predict_for(scored, history, ev)))
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
                send(format_alert(ipo, site_url), topic, post=post)
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
