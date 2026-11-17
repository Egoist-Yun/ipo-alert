from dataclasses import replace
from datetime import datetime

from ipo.config import DISCLAIMER, KST
from ipo.models import Ipo
from ipo.notify import (due_alerts, failure_alert, format_alert, load_state, mark_sent, save_state,
                        send)


def kst(y, m, d, h):
    return datetime(y, m, d, h, 0, tzinfo=KST)


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


def test_format_contains_disclaimer_click_and_lines():
    p = format_alert(NEXI, "https://x.github.io/ipo-alert/")
    assert p["title"] == "넥스아이 ⚠5개 · 청약 11/3~11/4"
    assert p["click"] == "https://x.github.io/ipo-alert/#2336"
    assert DISCLAIMER in p["message"]
    assert "공모가 위치" in p["message"] and "의무보유확약" in p["message"]
    assert "유통가능물량" not in p["message"]
    assert "비슷한 10개 중 7개 하락" in p["message"]
    assert "시초가 예상 +12% (±41%p) · 종가 예상 -9% (±59%p)" in p["message"]
    assert "확인 불가 1개" in p["message"]


def test_format_without_prediction_or_unknown():
    p = format_alert(replace(NEXI, prediction=None, unknown_count=0), "https://s/")
    assert "비슷한" not in p["message"] and "예상" not in p["message"] and "확인 불가" not in p["message"]


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


def test_title_with_zero_flags_but_unknowns_does_not_look_safe():
    p = format_alert(replace(NEXI, flag_count=0, unknown_count=4), "https://s/")
    assert p["title"] == "넥스아이 ⚠0개 · 확인 불가 4개 · 청약 11/3~11/4"


def test_format_shows_probability_and_conflict_line():
    pred = {"knn": None, "model": None, "prob": {"p_down": 0.31, "n": 260}, "conflict": True, "accuracy": None}
    p = format_alert(replace(NEXI, prediction=pred), "https://s/")
    assert "공모가 아래로 끝날 확률 31%" in p["message"]
    assert "신호와 예측이 엇갈려요" in p["message"]


def test_format_without_conflict_has_no_conflict_line():
    pred = {"knn": None, "model": None, "prob": {"p_down": 0.8, "n": 260}, "conflict": False, "accuracy": None}
    assert "엇갈려요" not in format_alert(replace(NEXI, prediction=pred), "https://s/")["message"]


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


def test_close_warning_line_and_title():
    pred = {"knn": None, "open": None, "close": None, "conflict": False, "accuracy": None,
            "prob": {"p_down": 0.35, "n": 260, "threshold": 0.3, "warn": True, "precision": 0.59, "recall": 0.72}}
    p = format_alert(replace(NEXI, prediction=pred), "https://s/")
    assert p["title"] == "넥스아이 ⚠5개 · 하락 경고 · 청약 11/3~11/4"
    assert "하락 경고: 공모가 아래로 끝날 확률 35% (경고 기준 30%)" in p["message"]


RISK = {"key": "lock_comp", "label": "의무보유확약 1% 미만 + 기관 경쟁률 300대 1 미만", "phase": "pre", "kind": "risk",
        "n": 24, "close_down": 0.75, "open_down": 0.5}
POST_RISK = {"key": "retail_lock", "label": "일반청약 경쟁률 100대 1 미만 + 의무보유확약 1% 미만", "phase": "post",
             "kind": "risk", "n": 24, "close_down": 0.88, "open_down": 0.58}
SAFE = {"key": "strong", "label": "기관 경쟁률 1000대 1 초과 + 의무보유확약 3% 이상", "phase": "pre", "kind": "safe",
        "n": 82, "close_down": 0.1, "open_down": 0.0}


def test_alert_shows_strongest_risk_pattern():
    p = format_alert(replace(NEXI, patterns=[SAFE, RISK]), "https://s/")
    assert "과거 하락 패턴: 의무보유확약 1% 미만 + 기관 경쟁률 300대 1 미만 (과거 24개 중 75%가 첫날 공모가 아래)" in p["message"]
    assert "하락이 드문" not in p["message"]


def test_alert_shows_safe_pattern_when_no_risk_pattern():
    p = format_alert(replace(NEXI, patterns=[SAFE]), "https://s/")
    assert "과거 하락이 드문 패턴: 기관 경쟁률 1000대 1 초과 + 의무보유확약 3% 이상 (과거 82개 중 10%만 첫날 공모가 아래)" in p["message"]


def test_pre_listing_alert_uses_open_rate_of_post_pattern():
    from ipo.notify import format_pre_alert
    p = format_pre_alert(replace(LISTING_SOON, patterns=[RISK, POST_RISK]), "https://s/")
    assert "과거 하락 패턴: 일반청약 경쟁률 100대 1 미만 + 의무보유확약 1% 미만 (과거 24개 중 58%가 시초가 공모가 아래)" in p["message"]
