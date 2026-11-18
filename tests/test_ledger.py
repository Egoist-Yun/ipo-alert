import json
from datetime import datetime

from ipo.config import KST
from ipo.ledger import (fill_results, ledger_markdown, load_ledger, record_predictions, save_ledger,
                        summarize, update_backtest_md)
from ipo.models import Ipo

PRE = {"prob": {"p_down": 0.6, "warn": True, "threshold": 0.35},
       "knn": {"n": 10, "down_count": 4, "median": 0.1}, "open_down": None}
POST = {**PRE, "open_down": {"p_down": 0.5, "warn": True, "threshold": 0.25}}
RISK_PRE = [{"key": "lock_comp", "kind": "risk", "phase": "pre"}]


def at(day, hour=10):
    return datetime(2026, 11, day, hour, 0, tzinfo=KST)


def stock(no=1, **kw):
    base = dict(no=no, name=f"S{no}", url="", final_price=10000, listing_date="2026-11-30", prediction=PRE,
                patterns=RISK_PRE)
    base.update(kw)
    return Ipo(**base)


def test_pre_prediction_is_saved_once_and_never_overwritten():
    led = {}
    assert record_predictions(led, [stock()], at(18), "m1") == 1
    rec = led["1"]["pre"]
    assert rec["p_down"] == 0.6 and rec["warn"] is True and rec["level"] == "strong" and rec["threshold"] == 0.35
    assert rec["knn"] == {"n": 10, "down_count": 4, "median": 0.1}
    assert rec["model"] == "m1" and rec["saved_at"].startswith("2026-11-18T10:00")
    changed = stock(prediction={**PRE, "prob": {"p_down": 0.1, "warn": False, "threshold": 0.35}})
    assert record_predictions(led, [changed], at(19), "m2") == 0
    assert led["1"]["pre"] == rec


def test_post_prediction_is_saved_separately_after_the_subscription_closes():
    led = {}
    record_predictions(led, [stock()], at(18), "m1")
    assert "post" not in led["1"]
    closed = stock(prediction=POST, retail_competition=900.0)
    assert record_predictions(led, [closed], at(25), "m1") == 1
    assert led["1"]["post"]["p_down"] == 0.5 and led["1"]["post"]["warn"] is True
    assert led["1"]["pre"]["saved_at"].startswith("2026-11-18")
    assert record_predictions(led, [closed], at(26), "m1") == 0


def test_nothing_is_saved_from_listing_day_9am_on():
    led = {}
    listing = stock(listing_date="2026-11-30")
    assert record_predictions(led, [listing], datetime(2026, 11, 30, 9, 0, tzinfo=KST), "m") == 0
    assert record_predictions(led, [listing], datetime(2026, 11, 30, 18, 0, tzinfo=KST), "m") == 0
    assert led == {}
    assert record_predictions(led, [listing], datetime(2026, 11, 30, 8, 59, tzinfo=KST), "m") == 1


def test_already_listed_stocks_and_old_dates_are_not_backfilled():
    led = {}
    listed = stock(no=2, first_close=12000, open_price=11000, listing_date="2026-11-20")
    assert record_predictions(led, [listed], at(18), "m") == 0
    assert record_predictions(led, [stock(no=3, prediction=None)], at(18), "m") == 0
    assert record_predictions(led, [stock(no=4, is_spac=True)], at(18), "m") == 0
    assert record_predictions({}, [stock()], datetime(2026, 11, 17, 10, 0, tzinfo=KST), "m") == 0
    assert led == {}


def test_results_are_filled_without_touching_predictions():
    led = {}
    record_predictions(led, [stock()], at(18), "m")
    before = json.dumps(led["1"]["pre"])
    assert fill_results(led, [stock()], at(30, 18)) == 0  # not listed yet
    listed = stock(open_price=9000, first_close=11000)
    assert fill_results(led, [listed], at(30, 18)) == 1
    r = led["1"]["result"]
    assert r["open_down"] is True and r["close_down"] is False
    assert round(r["open_return"], 2) == -0.10 and round(r["close_return"], 2) == 0.10
    assert json.dumps(led["1"]["pre"]) == before
    assert fill_results(led, [listed], at(30, 19)) == 0  # filled once


def entry(level, down_open, down_close, with_post=True):
    e = {"pre": {"warn": level is not None, "level": level},
         "result": {"open_down": down_open, "close_down": down_close}}
    if with_post:
        e["post"] = {"warn": level is not None, "level": level}
    return e


def test_summary_counts_warnings_and_declines_per_model():
    led = {"1": entry("strong", True, True), "2": entry("warn", False, True), "3": entry(None, False, True),
           "4": entry(None, False, False), "5": {"pre": {"warn": True, "level": "warn"}, "result": None}}
    s = summarize(led)
    pre = s["pre"]
    assert (pre["saved"], pre["resolved"], pre["pending"]) == (5, 4, 1)
    assert (pre["warned"], pre["caught"], pre["n_down"]) == (2, 2, 3)
    assert (pre["strong_warned"], pre["strong_caught"]) == (1, 1)
    post = s["post"]
    assert (post["warned"], post["caught"], post["n_down"]) == (2, 1, 1)
    assert pre["early"] is True  # fewer than 10 declines


def test_summary_is_not_early_with_ten_declines():
    led = {str(i): entry("warn", True, True) for i in range(10)}
    assert summarize(led)["pre"]["early"] is False


def test_markdown_table_uses_counts_not_percentages(tmp_path):
    led = {"1": entry("warn", True, True)}
    md = ledger_markdown(summarize(led))
    assert "경고 1개 중 1개 적중" in md and "하락 1개 중 1개 포착" in md and "아직 판단하기 일러요" in md
    assert "%" not in md
    p = tmp_path / "backtest.md"
    p.write_text("# 검증\n\n기존 내용\n", encoding="utf-8")
    update_backtest_md(p, md)
    update_backtest_md(p, md.replace("1개", "2개"))
    text = p.read_text(encoding="utf-8")
    assert "기존 내용" in text and text.count("실전 성적") == 1 and "2개" in text


def test_ledger_file_round_trip_and_missing_file(tmp_path):
    p = tmp_path / "predictions.json"
    assert load_ledger(p) == {}
    save_ledger(p, {"1": {"name": "A"}})
    assert load_ledger(p) == {"1": {"name": "A"}}
