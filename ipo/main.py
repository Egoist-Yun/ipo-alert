import json
import os
import sys
import traceback
from dataclasses import asdict, fields, replace
from datetime import datetime, timedelta
from pathlib import Path

import requests

from ipo import config
from ipo.collect import collect_current, detail_failure, detail_url, market_mood
from ipo.fetch import FetchError, get_html
from ipo.history import load_history, save_history, update_history
from ipo.notify import (Target, _line, _span, digest_run, due_alerts, failure_alert, format_digest, format_daily, format_pre_alert, group_alerts, load_state, mark_digest, mark_sent,
                        save_state,
                        send, target_from_env)
from ipo.patterns import match_patterns, pattern_stats, warning_level
from ipo.predict import _usable, calibrate, coverage_names, evaluate, predict_for, select_features
from ipo.ledger import (fill_results, ledger_markdown, load_ledger, model_id, record_predictions, save_ledger,
                        summarize, update_backtest_md)
from ipo.models import Ipo
from ipo.parse import is_missing_page
from ipo.signals import score

CALENDAR_DAYS_BACK = 90
MAX_VANISHED = 3  # more unchecked stocks than this gone from the lists at once: a site problem, not withdrawals
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


def _build(data_dir: Path, now_kst: datetime, fetch, failures: list | None = None) -> list:
    today = now_kst.date().isoformat()
    history_path = data_dir / "history.json"
    history = load_history(history_path) if history_path.exists() else []
    history = update_history(history, fetch=fetch, failures=failures)
    save_history(history_path, history)

    current = collect_current(fetch=fetch, today=today, failures=failures)
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
        out.append(replace(scored, prediction=pred, patterns=matched, warning=warning_level(pred, matched),
                           warning_pre=_warning_pre(pred, matched)))
    return sorted(out, key=lambda i: (i.sub_start, i.no))


def _previous_ipos(data_dir: Path, failures: list) -> list[Ipo]:
    """The stocks of the last run (data/ipos.json), read before this run overwrites it, row by row: a broken row is skipped
    and reported in `failures`, a file that cannot be read at all is reported once. No file: none, silently (first run)."""
    path = data_dir / "ipos.json"
    if not path.exists():
        return []
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))["ipos"]
        if not isinstance(rows, list):
            raise ValueError("ipos is not a list")
    except Exception as e:
        traceback.print_exc()
        failures.append({"no": 0, "name": "data/ipos.json", "error": f"{type(e).__name__}: {e}"})
        return []
    names = {f.name for f in fields(Ipo)}
    out = []
    for d in rows:
        try:
            out.append(Ipo(**{k: v for k, v in d.items() if k in names}))
        except Exception:
            traceback.print_exc()
            row = d if isinstance(d, dict) else {}
            failures.append({"no": row.get("no", 0), "name": row.get("name", "?"), "error": "이전 데이터 읽기 실패"})
    return out


def _carry_withdrawn(previous: list[Ipo], current: list[Ipo], history: list, now_kst: datetime, fetch, failures: list) -> list[Ipo]:
    """A stock that was on the calendar but is in no list any more (and has not listed, listing day not past) is either
    called off - its detail page answers "no such information" - or something else went wrong. Called off: it stays on the
    calendar marked `withdrawn` (checked once, then carried without asking again). Anything not confirmed is reported in
    `failures` and the stock is kept as it was, to be checked again next run. More than MAX_VANISHED unchecked stocks gone
    at once looks like a site problem, not many withdrawals: none is opened. A stock already marked withdrawn only follows the
    calendar cutoff. A stock not confirmed whose listing day has passed is not opened either: the history decides (listed:
    it keeps the result; no result there: reported once and dropped)."""
    today = now_kst.date().isoformat()
    cutoff = (now_kst.date() - timedelta(days=CALENDAR_DAYS_BACK)).isoformat()
    here = {i.no for i in current}
    away = [old for old in previous if old.no not in here and old.first_close is None]
    passed = lambda old: bool(old.listing_date and old.listing_date < today)
    late = [old for old in away if not old.withdrawn and passed(old)]
    gone = [old for old in away if old.withdrawn or not passed(old)]
    unchecked = [old for old in gone if not old.withdrawn]
    mass = len(unchecked) > MAX_VANISHED
    listed = {h.no: h for h in history if h.first_close is not None}
    carried = []
    for old in late:
        h = listed.get(old.no)
        if h is None:
            failures.append({"no": old.no, "name": old.name, "error": "상장일이 지났는데 결과 없음"})
        elif old.sub_start and old.sub_start >= cutoff:
            carried.append(replace(old, first_close=h.first_close, open_price=h.open_price))
    for old in gone:
        if not old.withdrawn:
            if mass:
                failures.append({"no": old.no, "name": old.name, "error": f"목록에서 한꺼번에 사라짐({len(unchecked)}개)"})
            else:
                try:
                    missing = is_missing_page(fetch(detail_url(old.no)))
                except FetchError as e:
                    failures.append(detail_failure(old.no, old.name, e))
                    missing = False
                else:
                    if not missing:
                        failures.append({"no": old.no, "name": old.name, "error": "목록에서 사라짐"})
                if missing:
                    old = replace(old, withdrawn=today, warning=None, warning_pre=None, prediction=None, patterns=[])
        if old.sub_start and old.sub_start >= cutoff:
            carried.append(old)
    return carried


def _withdrawn_alerts(data_dir: Path, ipos: list, target: Target, post) -> None:
    """One notice per withdrawn stock, remembered only after it was sent (a failed send is tried again next run)."""
    path = data_dir / "state.json"
    state = load_state(path)
    sent = set(state.get("sent", []))
    for ipo in ipos:
        key = f"withdrawn:{ipo.no}"
        if not ipo.withdrawn or key in sent:
            continue
        try:
            send({"title": config.APP_NAME, "message": _line("청약 철회", ipo.name, _span(ipo.sub_start, ipo.sub_end))}, target, post=post)
        except Exception:
            traceback.print_exc()
            continue
        mark_sent(state, [(key, ipo)])
        save_state(path, state)


def _warning_pre(pred: dict | None, matched: list[dict]) -> str | None:
    """The judgment of the pre-subscription model alone (the same rule as the ledger's 'pre' level), kept next to
    `warning` because after the subscription closes `warning` follows the open-price model and can differ."""
    prob = (pred or {}).get("prob")
    return warning_level({"prob": prob}, matched) if prob else None


def _update_ledger(data_dir: Path, ipos: list, now_kst: datetime, errors: list | None = None) -> dict | None:
    """Save new predictions, fill results, refresh the score. A failure here must never break the calendar:
    it is logged, appended to `errors` (reported in the payload and by an alert) and the run goes on."""
    try:
        path = data_dir / "predictions.json"
        ledger = load_ledger(path)
        record_predictions(ledger, ipos, now_kst, model_id(data_dir / "model.json"))
        fill_results(ledger, ipos, now_kst)
        save_ledger(path, ledger)
        summary = summarize(ledger)
        update_backtest_md(data_dir / "backtest.md", ledger_markdown(summary))
        return summary
    except Exception as e:
        traceback.print_exc()
        if errors is not None:
            errors.append(f"{type(e).__name__}: {e}")
        return None


def _problem_alerts(target: Target, failures: list, ledger_errors: list, post) -> None:
    """Short notices for problems that did not stop the run. A failed notice is only logged."""
    notices = []
    if failures:
        notices.append({"title": config.APP_NAME, "message": "상세 수집 일부 실패 · " + ", ".join(f["name"] for f in failures)[:300]})
    if ledger_errors:
        notices.append({"title": config.APP_NAME, "message": f"기록부 갱신 실패 · {ledger_errors[0][:300]}"})
    for notice in notices:
        try:
            send(notice, target, post=post)
        except Exception:
            traceback.print_exc()


def _send_alerts(data_dir: Path, ipos: list, target: Target, site_url: str, now_kst: datetime, post) -> None:
    """Result and eve alerts go out as one digest each, then the pre-listing alerts one by one. A key is remembered (and
    the state saved) only after its send succeeded, so a failed send is tried again on the next run."""
    path = data_dir / "state.json"
    state = load_state(path)
    morning = digest_run(state, now_kst)  # decided before anything is marked
    groups = group_alerts(due_alerts(ipos, state, now_kst))
    if morning:
        # The day's one alert (new results, today's subscriptions and listings); a failed send records nothing, so the next run tries again
        try:
            send(format_daily([ipo for _, ipo in groups["result"]], ipos, now_kst.date(), site_url), target, post=post)
        except Exception:
            traceback.print_exc()
        else:
            mark_sent(state, groups["result"])
            mark_digest(state, now_kst)
            save_state(path, state)
    for kind in ("result", "eve"):
        items = groups[kind]
        if not items or (kind == "result" and morning):    # on a morning the results went out inside the daily alert
            continue
        try:
            send(format_digest(kind, [ipo for _, ipo in items], site_url), target, post=post)
        except Exception:
            traceback.print_exc()
            continue
        mark_sent(state, items)
        save_state(path, state)
    for key, ipo in groups["pre"]:
        try:
            send(format_pre_alert(ipo, site_url), target, post=post)
        except Exception:
            traceback.print_exc()
            continue
        mark_sent(state, [(key, ipo)])
        save_state(path, state)
    save_state(path, state)


def run(data_dir: Path, target: Target | None, site_url: str, now_kst: datetime,
        fetch=get_html, post=requests.post) -> int:
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    try:
        raw_failures: list = []
        ledger_errors: list = []
        previous = _previous_ipos(data_dir, raw_failures)  # read before anything is overwritten
        ipos = _build(data_dir, now_kst, fetch, raw_failures)
        history_path = data_dir / "history.json"
        history = load_history(history_path) if history_path.exists() else []   # saved by _build just above
        ipos = sorted(ipos + _carry_withdrawn(previous, ipos, history, now_kst, fetch, raw_failures), key=lambda i: (i.sub_start or "", i.no))
        failures = list({(f["no"], f["name"]): f for f in raw_failures}.values())  # a stock can fail in both the history and the current pass
        payload = {"updated_at": now_kst.isoformat(), "ledger": _update_ledger(data_dir, ipos, now_kst, ledger_errors), "ipos": [asdict(i) for i in ipos]}
        if failures:
            payload["detail_failures"] = failures
        if ledger_errors:
            payload["ledger_error"] = ledger_errors[0]
        _atomic_write(data_dir / "ipos.json", json.dumps(payload, ensure_ascii=False))
    except Exception as e:
        traceback.print_exc()
        if target:
            try:
                send(failure_alert(f"{type(e).__name__}: {e}"), target, post=post)
            except Exception:
                traceback.print_exc()
        return 1

    if target:
        _problem_alerts(target, failures, ledger_errors, post)
        _withdrawn_alerts(data_dir, ipos, target, post)
        _send_alerts(data_dir, ipos, target, site_url, now_kst, post)
    return 0


def main() -> None:
    code = run(Path("data"), target_from_env(), os.environ.get("SITE_URL", ""), datetime.now(config.KST))
    sys.exit(code)


if __name__ == "__main__":
    main()
