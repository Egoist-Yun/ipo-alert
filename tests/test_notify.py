from dataclasses import replace
from datetime import datetime

from ipo.config import DISCLAIMER, KST
from ipo.models import Ipo
from ipo.notify import (digest_run, due_alerts, failure_alert, format_digest, group_alerts, load_state, mark_digest,
                        mark_sent, save_state, send)


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


def test_spac_and_no_result_do_not_alert():
    assert due_alerts([replace(NEXI, is_spac=True)], {"sent": []}, kst(2026, 10, 29, 18)) == []
    assert due_alerts([replace(NEXI, inst_competition=None)], {"sent": []}, kst(2026, 10, 29, 18)) == []


def test_send_posts_json():
    calls = []
    send({"title": "t"}, "topic-x", post=lambda url, json, timeout: calls.append((url, json)))
    assert calls[0][0] == "https://ntfy.sh" and calls[0][1]["topic"] == "topic-x"
    assert calls[0][1]["title"] == "t"


def test_failure_alert_title():
    assert failure_alert("boom")["title"] == "공모주 수집 실패"


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


def test_pre_listing_alert_text():
    from ipo.notify import format_pre_alert
    p = format_pre_alert(LISTING_SOON, "https://s/")
    assert p["title"] == "넥스아이 상장 전 · 시초가 하락 경고"
    assert "시초가 하락 확률 62% (경고 기준 30%)" in p["message"]
    assert "시초가 예상 7,120원 (-11%, ±37%p)" in p["message"]
    assert "일반청약 경쟁률 13대 1" in p["message"]
    assert "하락의 75%를 미리 잡았고, 경고의 82%가 맞았어요" in p["message"]
    assert DISCLAIMER in p["message"] and p["click"] == "https://s/#88"
    calm = replace(LISTING_SOON, prediction={**LISTING_SOON.prediction,
                                             "open_down": {**OPEN_DOWN, "p_down": 0.1, "warn": False}})
    assert format_pre_alert(calm, "https://s/")["title"] == "넥스아이 상장 전 · 시초가 예상"


RISK = {"key": "lock_comp", "label": "의무보유확약 1% 미만 + 기관 경쟁률 300대 1 미만", "phase": "pre", "kind": "risk",
        "n": 24, "close_down": 0.75, "open_down": 0.5}
POST_RISK = {"key": "retail_lock", "label": "일반청약 경쟁률 100대 1 미만 + 의무보유확약 1% 미만", "phase": "post",
             "kind": "risk", "n": 24, "close_down": 0.88, "open_down": 0.58}
SAFE = {"key": "strong", "label": "기관 경쟁률 1000대 1 초과 + 의무보유확약 3% 이상", "phase": "pre", "kind": "safe",
        "n": 82, "close_down": 0.1, "open_down": 0.0}


def test_pre_listing_alert_uses_open_rate_of_post_pattern():
    from ipo.notify import format_pre_alert
    p = format_pre_alert(replace(LISTING_SOON, patterns=[RISK, POST_RISK]), "https://s/")
    assert "과거 하락 패턴: 일반청약 경쟁률 100대 1 미만 + 의무보유확약 1% 미만 (과거 24개 중 58%가 시초가 공모가 아래)" in p["message"]


def test_pre_alert_title_names_the_strong_warning():
    from ipo.notify import format_pre_alert
    pre = format_pre_alert(replace(LISTING_SOON, warning="strong"), "https://s/")
    assert pre["title"] == "넥스아이 상장 전 · 시초가 강한 하락 경고"


def test_pre_alert_shows_the_safe_pattern_when_there_is_no_risk_pattern():
    from ipo.notify import format_pre_alert
    p = format_pre_alert(replace(LISTING_SOON, patterns=[SAFE]), "https://s/")
    assert "과거 하락이 드문 패턴: 기관 경쟁률 1000대 1 초과 + 의무보유확약 3% 이상 (과거 82개 중 0%만 시초가 공모가 아래)" in p["message"]


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
    assert p["title"] == "내일 청약 2건"


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
    body = p["message"].split("\n")
    assert p["title"] == "수요예측 결과 8건"
    assert body[:-1] == [                                                               # (g)
        "S1 · 강한 하락 경고 · 청약 11/20~11/30",
        "S3 · 하락 경고 · 청약 11/21~11/30",
        "S2 · 하락 경고 · 청약 11/22~11/30",
        "S4 · 하락 경고 · 청약 11/23~11/30",
        "S8 · 경고 없음 · 청약 11/17~11/30",
        "S7 · 경고 없음 · 청약 11/18~11/30",
        "S5 · 경고 없음 (신호 3개) · 청약 11/19~11/30",
        "S6 · 경고 없음 (확인 불가 2개) · 청약 11/19~11/30",
    ]
    assert body[-1] == DISCLAIMER


def test_digest_has_no_warning_symbol():
    p = format_digest("result", [NEXI, verdict_stock(2, "2026-11-20", warning="strong")], "https://s/")
    assert "⚠" not in p["title"] and "⚠" not in p["message"]                           # (h)


def test_digest_click_is_the_stock_for_one_and_the_front_page_for_several():
    one = format_digest("result", [NEXI], "https://x.github.io/ipo-alert/")
    assert one["title"] == "수요예측 결과 1건" and one["click"] == "https://x.github.io/ipo-alert/#2336"   # (i)
    many = format_digest("eve", [NEXI, stock(2)], "https://x.github.io/ipo-alert/")
    assert many["click"] == "https://x.github.io/ipo-alert/"


def test_every_digest_ends_with_the_disclaimer_line():
    for kind in ("result", "eve"):
        assert format_digest(kind, [NEXI, stock(2)], "https://s/")["message"].split("\n")[-1] == DISCLAIMER
