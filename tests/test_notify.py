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
           prediction={"knn": {"n": 10, "down_count": 7}, "model": {"return": -0.09, "mae": 0.18},
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
    assert "모델 예측 -9% (±18%p)" in p["message"]
    assert "확인 불가 1개" in p["message"]


def test_format_without_prediction_or_unknown():
    p = format_alert(replace(NEXI, prediction=None, unknown_count=0), "https://s/")
    assert "비슷한" not in p["message"] and "모델" not in p["message"] and "확인 불가" not in p["message"]


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
