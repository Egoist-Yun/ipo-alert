from dataclasses import replace
from datetime import date as date_, datetime

from ipo.config import APP_NAME, KST
from ipo.models import Ipo
from ipo.notify import (digest_run, due_alerts, failure_alert, format_digest, group_alerts, load_state, mark_digest,
                        mark_sent, save_state, send, Target, _line, _span, _verdict, format_daily, format_pre_alert)


def kst(y, m, d, h, minute=0):
    return datetime(y, m, d, h, minute, tzinfo=KST)


NEXI = Ipo(no=2336, name="넥스아이", url="https://38/2336", sub_start="2026-11-03", sub_end="2026-11-04",
           inst_competition=66.58, flag_count=5, unknown_count=1,
           signals=[
               {"key": "price_position", "label": "공모가 위치", "value": 8000, "flag": True},
               {"key": "lockup", "label": "의무보유확약", "value": 0.06, "flag": True},
               {"key": "mood", "label": "최근 시장 분위기", "value": None, "flag": None},
               {"key": "float", "label": "유통가능물량", "value": 10.0, "flag": False},
           ],
           prediction={"knn": {"n": 10, "down_count": 7},
                       "open": {"return": 0.12, "mae": 0.41}, "close": {"return": -0.09, "mae": 0.59},
                       "accuracy": None})


def test_result_alert_once():
    st = {"sent": []}
    first = due_alerts([NEXI], st, kst(2026, 10, 29, 18))
    assert [k for k, _ in first] == ["result:2336"]
    mark_sent(st, first)
    assert due_alerts([NEXI], st, kst(2026, 10, 29, 18)) == []


def test_eve_alert_across_month():
    ipo = replace(NEXI, no=77, sub_start="2026-11-27", sub_end="2026-11-30")
    st = {"sent": ["result:77"]}
    assert due_alerts([ipo], st, kst(2026, 11, 26, 8)) == []
    assert [k for k, _ in due_alerts([ipo], st, kst(2026, 11, 26, 18))] == ["eve:77"]


def test_eve_alert_not_on_other_days():
    ipo = replace(NEXI, no=77, sub_start="2026-11-27", sub_end="2026-11-30")
    st = {"sent": ["result:77"]}
    assert due_alerts([ipo], st, kst(2026, 11, 25, 18)) == []
    assert due_alerts([ipo], st, kst(2026, 11, 27, 18)) == []


def test_zero_flag_still_alerts():
    ipo = replace(NEXI, flag_count=0)
    assert due_alerts([ipo], {"sent": []}, kst(2026, 10, 29, 18))


def test_spac_does_not_alert_and_no_result_means_no_result_or_pre_alert():
    assert due_alerts([replace(NEXI, is_spac=True)], {"sent": []}, kst(2026, 10, 29, 18)) == []
    assert due_alerts([replace(NEXI, inst_competition=None)], {"sent": []}, kst(2026, 10, 29, 18)) == []     # not the eve yet (sub 11/3)
    waiting = replace(LISTING_SOON, inst_competition=None)                                                      # (pre needs a result too)
    assert due_alerts([waiting], {"sent": []}, kst(2026, 11, 6, 18)) == []
    assert due_alerts([replace(NEXI, is_spac=True, inst_competition=None, sub_start="2026-10-30")], {"sent": []}, kst(2026, 10, 29, 18)) == []
    assert due_alerts([replace(NEXI, withdrawn=True, inst_competition=None, sub_start="2026-10-30")], {"sent": []}, kst(2026, 10, 29, 18)) == []


def test_send_posts_json():
    calls = []
    send({"title": "t"}, Target(topic="topic-x"), post=lambda url, json, timeout: calls.append((url, json)))
    assert calls[0][0] == "https://ntfy.sh" and calls[0][1]["topic"] == "topic-x"
    assert calls[0][1]["title"] == "t"


def test_failure_alert_is_titled_with_the_app_name_and_cuts_the_reason_at_300_characters():
    assert failure_alert("boom") == {"title": "공모주 달력", "message": "수집 실패 · boom"}
    assert failure_alert("x" * 500)["message"] == "수집 실패 · " + "x" * 300


def test_state_roundtrip_and_missing_file(tmp_path):
    assert load_state(tmp_path / "none.json") == {"sent": []}
    save_state(tmp_path / "s.json", {"sent": ["a"]})
    assert load_state(tmp_path / "s.json") == {"sent": ["a"]}


OPEN_DOWN = {"p_down": 0.62, "threshold": 0.3, "warn": True, "precision": 0.82, "recall": 0.75, "n": 880}
LISTING_SOON = replace(NEXI, no=88, sub_start="2026-11-03", sub_end="2026-11-04", listing_date="2026-11-12",
                       retail_competition=13.26,
                       prediction={"knn": None, "close": None, "prob": None, "conflict": False, "accuracy": None,
                                   "open": {"return": -0.11, "price": 7120, "mae": 0.37, "direction_acc": 0.9,
                                            "uses_retail": True},
                                   "open_down": OPEN_DOWN})


def test_pre_listing_alert_after_subscription_once():
    st = {"sent": ["result:88"]}
    due = due_alerts([LISTING_SOON], st, kst(2026, 11, 6, 18))
    assert [k for k, _ in due] == ["pre:88"]
    mark_sent(st, due)
    assert due_alerts([LISTING_SOON], st, kst(2026, 11, 7, 18)) == []


def test_no_pre_listing_alert_once_listed_or_before_subscription():
    st = {"sent": ["result:88"]}
    assert due_alerts([replace(LISTING_SOON, first_close=4810)], st, kst(2026, 11, 6, 18)) == []
    no_retail = replace(LISTING_SOON, prediction={**LISTING_SOON.prediction, "open_down": None})
    assert [k for k, _ in due_alerts([no_retail], st, kst(2026, 11, 6, 18))] == []


def test_pre_listing_alert_is_three_short_lines_titled_with_the_app_name():
    p = format_pre_alert(LISTING_SOON, "https://s/")
    assert p["title"] == "공모주 달력" and p["click"] == "https://s/#88"
    assert p["message"].split(chr(10)) == ["넥스아이 상장 전 · 시초가 경고", "하락 확률 62% (기준 30%)", "예상 시초가 7,120원 (-11%)"]


def test_pre_alert_first_line_says_strong_warn_or_nothing():
    strong = format_pre_alert(replace(LISTING_SOON, warning="strong"), "https://s/")["message"].split(chr(10))
    assert strong[0] == "넥스아이 상장 전 · 시초가 강한 경고"
    calm = replace(LISTING_SOON, prediction={**LISTING_SOON.prediction, "open_down": {**OPEN_DOWN, "p_down": 0.1, "warn": False}})
    lines = format_pre_alert(calm, "https://s/")["message"].split(chr(10))
    assert lines == ["넥스아이 상장 전", "하락 확률 10% (기준 30%)", "예상 시초가 7,120원 (-11%)"]


def test_pre_alert_without_an_open_price_has_two_lines_and_never_the_old_extra_lines():
    no_open = replace(LISTING_SOON, patterns=[{"kind": "risk", "label": "x", "n": 24, "open_down": 0.5}],
                      prediction={**LISTING_SOON.prediction, "open": None})
    lines = format_pre_alert(no_open, "https://s/")["message"].split(chr(10))
    assert lines == ["넥스아이 상장 전 · 시초가 경고", "하락 확률 62% (기준 30%)"]      # no pattern, retail-competition or validation line, no ±mae


# ---- result digest: one morning summary instead of one alert per stock ----

def stock(no, **kw):
    base = dict(no=no, name=f"종목{no}", sub_start="2026-11-03", sub_end="2026-11-04")
    return replace(NEXI, **{**base, **kw})


def test_result_digest_not_before_6am(tmp_path):
    assert due_alerts([NEXI], {"sent": []}, kst(2026, 10, 29, 5, 59)) == []          # (a)


def test_result_digest_first_run_from_6am_and_digest_date_is_saved():
    st = {"sent": []}
    assert digest_run(st, kst(2026, 10, 29, 6, 0)) is True
    due = due_alerts([NEXI], st, kst(2026, 10, 29, 6, 0))
    assert [k for k, _ in due] == ["result:2336"]                                      # (b)
    mark_sent(st, due)
    mark_digest(st, kst(2026, 10, 29, 6, 0))
    assert st["digest_date"] == "2026-10-29"
    assert digest_run(st, kst(2026, 10, 29, 18, 0)) is False
    assert digest_run(st, kst(2026, 10, 30, 6, 0)) is True


def test_result_digest_once_a_day_new_results_wait_for_tomorrow_morning():
    st = {"sent": [], "digest_date": "2026-10-29"}
    late = stock(5)                                                                   # (c) sub_start 11/3 is not urgent
    assert due_alerts([late], st, kst(2026, 10, 29, 18)) == []
    assert [k for k, _ in due_alerts([late], st, kst(2026, 10, 30, 6))] == ["result:5"]


def test_result_digest_urgent_when_the_subscription_starts_today_or_tomorrow():
    st = {"sent": [], "digest_date": "2026-10-29"}
    tomorrow = stock(6, sub_start="2026-10-30", sub_end="2026-10-31")
    today = stock(7, sub_start="2026-10-29", sub_end="2026-10-30")
    not_urgent = stock(8, sub_start="2026-10-31", sub_end="2026-11-02")
    due = due_alerts([tomorrow, today, not_urgent], st, kst(2026, 10, 29, 18))
    assert [k for k, _ in due if k.startswith("result:")] == ["result:6", "result:7"]   # (d) the eve alert of 6 is a separate kind
    assert [k for k, _ in due_alerts([tomorrow], {"sent": []}, kst(2026, 10, 29, 5, 59))] == ["result:6"]   # urgent even before 6am
    assert digest_run({"sent": [], "digest_date": "2026-10-29"}, kst(2026, 10, 29, 18)) is False          # urgent sends never count as the digest


def test_result_digest_a_late_first_run_still_sends():
    assert [k for k, _ in due_alerts([NEXI], {"sent": []}, kst(2026, 10, 29, 12, 58))] == ["result:2336"]    # (e)


def test_eve_digest_groups_all_eve_stocks_into_one_alert():
    a = stock(11, sub_start="2026-11-27", sub_end="2026-11-30")
    b = stock(12, sub_start="2026-11-27", sub_end="2026-12-01")
    st = {"sent": ["result:11", "result:12"]}
    groups = group_alerts(due_alerts([a, b], st, kst(2026, 11, 26, 18)))
    assert [i.no for _, i in groups["eve"]] == [11, 12] and groups["result"] == [] and groups["pre"] == []
    p = format_digest("eve", [i for _, i in groups["eve"]], "https://s/")           # (f)
    assert p["title"] == "공모주 달력" and p["message"].split(chr(10)) == ["내일 청약 · 종목11", "내일 청약 · 종목12"]


def verdict_stock(no, sub_start, **kw):
    base = dict(no=no, name=f"S{no}", sub_start=sub_start, sub_end="2026-11-30", flag_count=0, unknown_count=0,
                signals=[], prediction=None, warning=None)
    return replace(NEXI, **{**base, **kw})


def test_digest_verdict_wording_and_order():
    strong = verdict_stock(1, "2026-11-20", warning="strong")
    warn = verdict_stock(2, "2026-11-22", warning="warn")
    model_warn = verdict_stock(3, "2026-11-21", prediction={"prob": {"warn": True}})
    after_sub = verdict_stock(4, "2026-11-23", prediction={"prob": {"warn": False}, "open_down": {"warn": True}})
    signals = verdict_stock(5, "2026-11-19", flag_count=3)
    unknown = verdict_stock(6, "2026-11-19", unknown_count=2)
    clean = verdict_stock(7, "2026-11-18")
    one_unknown = verdict_stock(8, "2026-11-17", unknown_count=1)
    p = format_digest("result", [clean, signals, warn, strong, unknown, model_warn, after_sub, one_unknown], "https://s/")
    assert p["title"] == "공모주 달력"
    assert p["message"].split(chr(10)) == [                                              # (g) no header line, no disclaimer
        "수요예측 결과 · S1 · 강한 경고 · 청약 11/20~30",
        "수요예측 결과 · S3 · 경고 · 청약 11/21~30",
        "수요예측 결과 · S2 · 경고 · 청약 11/22~30",
        "수요예측 결과 · S4 · 경고 · 청약 11/23~30",
        "수요예측 결과 · S8 · 청약 11/17~30",
        "수요예측 결과 · S7 · 청약 11/18~30",
        "수요예측 결과 · S5 · 청약 11/19~30",
        "수요예측 결과 · S6 · 청약 11/19~30",
    ]


def test_digest_has_no_warning_symbol():
    p = format_digest("result", [NEXI, verdict_stock(2, "2026-11-20", warning="strong")], "https://s/")
    assert "⚠" not in p["title"] and "⚠" not in p["message"]                           # (h)


def test_digest_click_is_the_stock_for_one_and_the_front_page_for_several():
    one = format_digest("result", [NEXI], "https://x.github.io/ipo-alert/")
    assert one["title"] == "공모주 달력" and one["click"] == "https://x.github.io/ipo-alert/#2336"   # (i)
    many = format_digest("eve", [NEXI, stock(2)], "https://x.github.io/ipo-alert/")
    assert many["click"] == "https://x.github.io/ipo-alert/"


def test_no_alert_carries_the_disclaimer_line():
    from datetime import date
    texts = [format_digest(k, [NEXI, stock(2)], "https://s/")["message"] for k in ("result", "eve")]
    texts.append(format_daily([NEXI], [NEXI], date(2026, 10, 29), "https://s/")["message"])
    texts.append(format_daily([], [], date(2026, 10, 29), "https://s/")["message"])
    texts.append(format_pre_alert(LISTING_SOON, "https://s/")["message"])
    texts.append(failure_alert("boom")["message"])
    for text in texts:
        assert "투자 권유" not in text and "본인이 하세요" not in text
    import ipo.config
    assert not hasattr(ipo.config, "DISCLAIMER")


def test_every_alert_is_titled_with_the_app_name():
    from datetime import date
    alerts = [format_digest("result", [NEXI], "https://s/"), format_digest("eve", [NEXI, stock(2)], "https://s/"),
              format_daily([NEXI], [NEXI], date(2026, 10, 29), "https://s/"), format_daily([], [], date(2026, 10, 29), "https://s/"),
              format_pre_alert(LISTING_SOON, "https://s/"), failure_alert("boom")]
    assert {a["title"] for a in alerts} == {"공모주 달력"} == {APP_NAME}


def test_a_stock_without_a_warning_has_no_trailing_separator():
    clean = verdict_stock(7, "2026-11-18")
    assert _verdict(clean) == (2, "")
    for kind in ("result", "eve"):
        assert not any(l.endswith(" ·") or l.endswith("· ") for l in format_digest(kind, [clean], "https://s/")["message"].split(chr(10)))
    assert format_digest("eve", [clean], "https://s/")["message"] == "내일 청약 · S7"
    assert _line("결과", "S7", "") == "결과 · S7"


def test_format_daily_is_three_counts_that_differ_per_line():
    today = date_(2026, 11, 24)
    starts_today = [verdict_stock(i, "2026-11-24") for i in (1, 2)]                    # two subscriptions start today
    running = verdict_stock(3, "2026-11-23", sub_end="2026-11-25")                      # mid-period: not counted
    lists_today = verdict_stock(4, "2026-11-10", sub_end="2026-11-11", listing_date="2026-11-24")
    results = [verdict_stock(5, "2026-11-26"), verdict_stock(6, "2026-11-27"), verdict_stock(7, "2026-11-28")]
    p = format_daily(results, starts_today + [running, lists_today], today, "https://x.github.io/ipo/")
    assert p == {"title": "공모주 달력", "click": "https://x.github.io/ipo/",
                 "message": chr(10).join(["수요예측 : 3건", "청약시작 : 2건", "금일상장 : 1건"])}


def test_format_daily_with_nothing_sends_the_three_lines_with_zeros():
    p = format_daily([], [], date_(2026, 11, 24), "https://s/")
    assert p["message"].split(chr(10)) == ["수요예측 : 0건", "청약시작 : 0건", "금일상장 : 0건"] and p["click"] == "https://s/"


def test_format_daily_does_not_count_spacs_or_withdrawn_and_not_mid_period_days():
    today = date_(2026, 11, 24)
    ipos = [verdict_stock(1, "2026-11-24", is_spac=True), verdict_stock(2, "2026-11-24", withdrawn=True),
            verdict_stock(3, "2026-11-24"), verdict_stock(4, "2026-11-20", listing_date="2026-11-24", is_spac=True),
            verdict_stock(5, "2026-11-20", listing_date="2026-11-24", withdrawn=True),
            verdict_stock(6, "2026-11-20", sub_end="2026-11-26")]
    assert format_daily([], ipos, today, "https://s/")["message"].split(chr(10)) == ["수요예측 : 0건", "청약시작 : 1건", "금일상장 : 0건"]


def test_span_collapses_the_month_when_it_is_the_same_and_is_none_without_dates():
    assert _span("2026-11-18", "2026-11-19") == "11/18~19"
    assert _span("2026-11-28", "2026-12-01") == "11/28~12/1"
    assert _span("2026-12-30", "2027-01-02") == "12/30~1/2"
    assert _span("2026-11-18", "2026-11-18") == "11/18"
    assert _span(None, "2026-11-19") is None and _span("2026-11-18", None) is None and _span(None, None) is None


def test_the_result_line_drops_the_span_when_a_date_is_missing():
    p = format_digest("result", [verdict_stock(7, None, warning="strong")], "https://s/")
    assert p["message"] == "수요예측 결과 · S7 · 강한 경고"


KMF = dict(no=90, name="케이엠에프", sub_start="2026-11-24", sub_end="2026-11-25", inst_competition=None, flag_count=0,
           unknown_count=0, signals=[], prediction=None, warning=None)


def test_eve_alert_goes_out_before_the_demand_forecast_result_but_result_and_pre_do_not():
    ipo = replace(NEXI, **KMF)
    due = due_alerts([ipo], {"sent": []}, kst(2026, 11, 23, 12, 30))
    assert [k for k, _ in due] == ["eve:90"]                                           # (a)
    assert due_alerts([ipo], {"sent": []}, kst(2026, 11, 23, 11, 59)) == []            # still not before 12:00


def test_eve_digest_line_says_the_result_is_not_there_yet_and_sorts_after_stocks_with_a_verdict():
    waiting = replace(NEXI, **KMF)
    clean = verdict_stock(7, "2026-11-24")
    p = format_digest("eve", [waiting, clean], "https://s/")
    body = p["message"].split(chr(10))
    assert body[0] == "내일 청약 · S7"                                                  # (b)
    assert body == ["내일 청약 · S7", "내일 청약 · 케이엠에프 · 결과 전"]
