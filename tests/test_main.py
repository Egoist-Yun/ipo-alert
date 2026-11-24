import json
from datetime import datetime

import pytest

from ipo.config import KST
from ipo.main import run
from ipo.notify import Target
from tests.helpers import BARE_DETAIL, load

NOW = datetime(2026, 11, 17, 18, 0, tzinfo=KST)
NL = chr(10)
PAGES = {
    "index.htm?o=k": load("schedule"),
    "index.htm?o=r1": load("demand"),
    "o=nw": load("listing"),
    "no=2336": load("detail_2336"),
    "no=2352": load("detail_2352"),
}


def fake_fetch(url):
    for key, html in PAGES.items():
        if key in url:
            return html
    return BARE_DETAIL


class Rec:
    def __init__(self):
        self.calls = []

    def __call__(self, url, json, timeout):
        self.calls.append(json)


def _kind(call):
    """Every alert is titled with the app name, so what an alert is shows in its first line."""
    first = call["message"].split(chr(10))[0]
    if first.startswith("수요예측 결과 "):
        return "result"
    if first.startswith("내일 청약 "):
        return "eve"
    if first.startswith("수요예측 :"):
        return "daily"
    return "other"


def _kinds(calls):
    return [_kind(c) for c in calls]


def test_run_writes_ipos_json_and_alerts_once(tmp_path):
    rec = Rec()
    assert run(tmp_path, Target(topic="t"), "https://s/", NOW, fetch=fake_fetch, post=rec) == 0
    data = json.loads((tmp_path / "ipos.json").read_text("utf-8"))
    names = [i["name"] for i in data["ipos"]]
    assert "유캐스트" in names
    assert data["updated_at"].startswith("2026-11-17T18:00")
    assert "disclaimer" not in data and "투자 권유" not in json.dumps(data, ensure_ascii=False)   # the app no longer shows one
    ucast = next(i for i in data["ipos"] if i["name"] == "유캐스트")
    assert ucast["flag_count"] >= 1 and ucast["prediction"] is not None
    daily = [c for c in rec.calls if _kind(c) == "daily"]
    assert len(daily) == 1 and daily[0]["message"].split(chr(10))[0] == "수요예측 : 1건"   # one daily alert, not one alert per stock
    assert "result" not in _kinds(rec.calls) and {c["title"] for c in rec.calls} == {"공모주 달력"}   # (the urgent-only digest is not used on a morning run)
    assert not any("⚠" in c["title"] or "⚠" in c["message"] for c in rec.calls)
    state = json.loads((tmp_path / "state.json").read_text("utf-8"))
    assert state["digest_date"] == "2026-11-17" and any(k.startswith("result:") for k in state["sent"])
    assert (tmp_path / "history.json").exists() and (tmp_path / "state.json").exists()
    before = len(rec.calls)
    assert run(tmp_path, Target(topic="t"), "https://s/", NOW, fetch=fake_fetch, post=rec) == 0
    assert len(rec.calls) == before


def test_run_without_topic_sends_nothing(tmp_path):
    rec = Rec()
    assert run(tmp_path, None, "", NOW, fetch=fake_fetch, post=rec) == 0
    assert rec.calls == [] and (tmp_path / "ipos.json").exists()


def test_failure_keeps_old_file_and_alerts(tmp_path):
    (tmp_path / "ipos.json").write_text('{"ipos":[{"no":1}]}', "utf-8")
    rec = Rec()
    code = run(tmp_path, Target(topic="t"), "https://s/", NOW, fetch=lambda u: "<html></html>", post=rec)
    assert code != 0
    assert json.loads((tmp_path / "ipos.json").read_text("utf-8"))["ipos"] == [{"no": 1}]
    assert (rec.calls[-1]["title"], rec.calls[-1]["message"]) == ("공모주 달력", "앱 정보가 최신이 아닐 수 있어요. 다음 갱신 때 다시 시도해요.")


def test_quiet_hours_failure_keeps_old_file_without_alerting(tmp_path, capsys):
    previous = '{"ipos":[]}'
    (tmp_path / "ipos.json").write_text(previous, "utf-8")
    rec = Rec()
    code = run(tmp_path, Target(topic="t"), "", NOW.replace(hour=3), fetch=lambda u: "<html></html>", post=rec)
    assert code == 1
    assert rec.calls == []
    assert (tmp_path / "ipos.json").read_text("utf-8") == previous
    assert capsys.readouterr().out.count("quiet hours (22-07 KST): alerts deferred") == 1


def test_calendar_range_drops_old_stocks(tmp_path):
    run(tmp_path, None, "", NOW, fetch=fake_fetch, post=Rec())
    data = json.loads((tmp_path / "ipos.json").read_text("utf-8"))
    assert all(i["sub_start"] and i["sub_start"] >= "2026-08-19" for i in data["ipos"])


def test_already_listed_stock_gets_no_prediction(tmp_path):
    run(tmp_path, None, "", NOW, fetch=fake_fetch, post=Rec())
    data = json.loads((tmp_path / "ipos.json").read_text("utf-8"))
    nexi = next(i for i in data["ipos"] if i["name"] == "넥스아이")
    assert nexi["first_close"] == 4810 and nexi["prediction"] is None
    ucast = next(i for i in data["ipos"] if i["name"] == "유캐스트")
    assert ucast["prediction"] is not None


def test_listing_result_is_filled_from_history_when_tables_lack_it(tmp_path):
    from ipo.history import save_history
    from ipo.models import Ipo
    save_history(tmp_path / "history.json", [Ipo(no=2352, name="유캐스트", url="", listing_date="2026-11-30",
                                                 final_price=19000, open_price=25000, first_close=21000)])
    run(tmp_path, None, "", NOW, fetch=fake_fetch, post=Rec())
    data = json.loads((tmp_path / "ipos.json").read_text("utf-8"))
    ucast = next(i for i in data["ipos"] if i["no"] == 2352)
    assert (ucast["open_price"], ucast["first_close"]) == (25000, 21000) and ucast["prediction"] is None



def test_every_scored_stock_carries_a_pattern_list(tmp_path):
    run(tmp_path, None, "", NOW, fetch=fake_fetch, post=Rec())
    data = json.loads((tmp_path / "ipos.json").read_text("utf-8"))
    assert all(isinstance(i["patterns"], list) for i in data["ipos"])



def test_every_stock_has_a_warning_level_field(tmp_path):
    run(tmp_path, None, "", NOW, fetch=fake_fetch, post=Rec())
    data = json.loads((tmp_path / "ipos.json").read_text("utf-8"))
    assert all(i["warning"] in (None, "warn", "strong") for i in data["ipos"])


def test_model_config_recomputes_a_cache_saved_before_counts_and_intervals(tmp_path, monkeypatch):
    import json
    from ipo import main
    old = {"names": ["comp"], "n": 100, "calibration": {"close": {"threshold": 0.3, "test": {}}}}
    (tmp_path / "model.json").write_text(json.dumps(old), encoding="utf-8")
    fresh = {"close": {"threshold": 0.35, "test": {"caught": 1}}, "interval": {"close": {}}}
    monkeypatch.setattr(main, "_usable", lambda h: list(range(100)))
    monkeypatch.setattr(main, "select_features", lambda recent: ["comp"])
    monkeypatch.setattr(main, "calibrate", lambda full, recent, names: fresh)
    names, cal = main._model_config(tmp_path, [], [])
    assert cal == fresh
    names, cal = main._model_config(tmp_path, [], [])  # now cached and complete
    assert cal == fresh


def test_run_records_predictions_and_reports_the_ledger_score(tmp_path):
    now = datetime(2026, 11, 18, 18, 0, tzinfo=KST)
    assert run(tmp_path, None, "", now, fetch=fake_fetch, post=Rec()) == 0
    led = json.loads((tmp_path / "predictions.json").read_text("utf-8"))
    data = json.loads((tmp_path / "ipos.json").read_text("utf-8"))
    assert data["ledger"]["pre"]["saved"] == len([e for e in led.values() if "pre" in e])
    assert all(e["pre"]["saved_at"].startswith("2026-11-18") for e in led.values() if "pre" in e)
    assert "실전 성적" in (tmp_path / "backtest.md").read_text("utf-8")
    before = (tmp_path / "predictions.json").read_text("utf-8")
    assert run(tmp_path, None, "", now, fetch=fake_fetch, post=Rec()) == 0
    assert (tmp_path / "predictions.json").read_text("utf-8") == before


def test_a_ledger_failure_never_breaks_the_calendar(tmp_path, monkeypatch):
    from ipo import main
    monkeypatch.setattr(main, "record_predictions", lambda *a, **k: 1 / 0)
    assert run(tmp_path, None, "", NOW, fetch=fake_fetch, post=Rec()) == 0
    data = json.loads((tmp_path / "ipos.json").read_text("utf-8"))
    assert data["ledger"] is None and data["ipos"]


def test_a_failed_digest_send_keeps_the_keys_and_the_digest_date_unchanged(tmp_path):
    def boom(url, json, timeout):
        raise RuntimeError("ntfy down")
    assert run(tmp_path, Target(topic="t"), "https://s/", NOW, fetch=fake_fetch, post=boom) == 0
    state = json.loads((tmp_path / "state.json").read_text("utf-8")) if (tmp_path / "state.json").exists() else {"sent": []}
    assert not any(k.startswith(("result:", "eve:")) for k in state.get("sent", []))
    assert "digest_date" not in state
    rec = Rec()                                    # the next run (ntfy back) sends the same digest
    assert run(tmp_path, Target(topic="t"), "https://s/", NOW, fetch=fake_fetch, post=rec) == 0
    assert "daily" in _kinds(rec.calls)


@pytest.mark.parametrize("hour,minute,quiet", [(21, 59, False), (22, 0, True), (6, 59, True), (7, 0, False)])
def test_quiet_hours_boundaries(tmp_path, hour, minute, quiet):
    from ipo import main

    now = NOW.replace(hour=hour, minute=minute)
    rec = Rec()
    assert run(tmp_path, Target(topic="t"), "", now, fetch=fake_fetch, post=rec) == 0
    if quiet:
        assert rec.calls == []
    else:
        assert "daily" in _kinds(rec.calls)
    assert main.quiet_hours(now) is quiet


def test_quiet_hours_defer_result_and_withdrawal_until_morning(tmp_path, capsys):
    previous = {"no": 9999, "name": "철회종목", "url": "", "sub_start": "2026-11-18", "withdrawn": "2026-11-17"}
    (tmp_path / "ipos.json").write_text(json.dumps({"ipos": [previous]}), "utf-8")
    state_path = tmp_path / "state.json"
    state_path.write_text("{}", "utf-8")
    rec = Rec()
    target = Target(topic="t")
    assert run(tmp_path, target, "", NOW.replace(hour=3), fetch=fake_fetch, post=rec) == 0
    assert rec.calls == []
    assert _state(tmp_path) == {}
    data = json.loads((tmp_path / "ipos.json").read_text("utf-8"))
    assert data["updated_at"] == "2026-11-17T03:00:00+09:00"
    assert any(i["no"] == 9999 and i["withdrawn"] for i in data["ipos"])
    assert (tmp_path / "history.json").exists() and (tmp_path / "predictions.json").exists()
    assert capsys.readouterr().out.count("quiet hours (22-07 KST): alerts deferred") == 1

    assert run(tmp_path, target, "", NOW.replace(hour=8), fetch=fake_fetch, post=rec) == 0
    assert any(c["message"].startswith("청약 철회") and "철회종목" in c["message"] for c in rec.calls)
    assert [c["message"].splitlines()[0] for c in rec.calls if _kind(c) == "daily"] == ["수요예측 : 1건"]
    state = _state(tmp_path)
    assert {"result:2352", "withdrawn:9999"} <= set(state["sent"])
    assert state["digest_date"] == "2026-11-17"


@pytest.mark.parametrize("hour,expected_alerts", [(3, 0), (8, 1)])
def test_main_respects_quiet_hours_for_invalid_fcm_warning(monkeypatch, hour, expected_alerts):
    from ipo import main, notify

    class Clock(datetime):
        @classmethod
        def now(cls, tz):
            return NOW.replace(hour=hour)

    alerts = []
    monkeypatch.setenv("NTFY_TOPIC", "t")
    monkeypatch.setenv("FCM_SERVICE_ACCOUNT", "invalid-json")
    monkeypatch.setattr(main, "datetime", Clock)
    monkeypatch.setattr(main, "run", lambda *args: 0)
    monkeypatch.setattr(notify, "_ntfy", lambda payload, topic, post: alerts.append(payload))
    with pytest.raises(SystemExit) as exc:
        main.main()
    assert exc.value.code == 0
    assert len(alerts) == expected_alerts


def _digest_ipo(no, **kw):
    from dataclasses import replace
    from tests.test_notify import NEXI
    base = dict(no=no, name=f"종목{no}", sub_start="2026-11-25", sub_end="2026-11-26", flag_count=0, unknown_count=0,
                signals=[], prediction=None, warning=None)
    return replace(NEXI, **{**base, **kw})


def _calls():
    calls = []
    return calls, lambda url, json, timeout: calls.append(json)


def test_a_morning_run_without_results_still_sends_the_daily_alert_once_so_the_afternoon_waits(tmp_path):
    from ipo.main import _send_alerts
    calls, post = _calls()
    waiting = _digest_ipo(1, inst_competition=None)                      # no demand result yet
    _send_alerts(tmp_path, [waiting], Target(topic="t"), "https://s/", datetime(2026, 11, 19, 8, 17, tzinfo=KST), post)
    assert _kinds(calls) == ["daily"]                                     # (a) no new result: the daily alert still goes out
    assert json.loads((tmp_path / "state.json").read_text("utf-8"))["digest_date"] == "2026-11-19"   # and the day is recorded
    late = _digest_ipo(1)                                                # the result arrives in the afternoon
    _send_alerts(tmp_path, [late], Target(topic="t"), "https://s/", datetime(2026, 11, 19, 17, 47, tzinfo=KST), post)
    assert _kinds(calls) == ["daily"]                                     # not today: no second alert, the result waits for tomorrow's morning
    _send_alerts(tmp_path, [late], Target(topic="t"), "https://s/", datetime(2026, 11, 20, 8, 17, tzinfo=KST), post)
    assert _kinds(calls) == ["daily", "daily"]
    assert calls[0]["message"].split(chr(10))[0] == "수요예측 : 0건" and calls[1]["message"].split(chr(10))[0] == "수요예측 : 1건"


def test_an_urgent_result_still_goes_out_in_the_afternoon_after_an_empty_morning(tmp_path):
    from ipo.main import _send_alerts
    calls, post = _calls()
    _send_alerts(tmp_path, [], Target(topic="t"), "https://s/", datetime(2026, 11, 19, 8, 17, tzinfo=KST), post)
    urgent = _digest_ipo(2, sub_start="2026-11-20", sub_end="2026-11-21")   # subscribes tomorrow
    _send_alerts(tmp_path, [urgent], Target(topic="t"), "https://s/", datetime(2026, 11, 19, 17, 47, tzinfo=KST), post)
    assert "result" in _kinds(calls)


def test_a_failed_morning_send_is_not_recorded_and_the_afternoon_run_tries_again(tmp_path):
    from ipo.main import _send_alerts
    ipo = _digest_ipo(3)

    def boom(url, json, timeout):
        raise RuntimeError("ntfy down")
    _send_alerts(tmp_path, [ipo], Target(topic="t"), "https://s/", datetime(2026, 11, 19, 8, 17, tzinfo=KST), boom)
    state = json.loads((tmp_path / "state.json").read_text("utf-8"))
    assert "digest_date" not in state and "result:3" not in state["sent"]                       # (b)
    calls, post = _calls()
    _send_alerts(tmp_path, [ipo], Target(topic="t"), "https://s/", datetime(2026, 11, 19, 17, 47, tzinfo=KST), post)
    assert _kinds(calls) == ["daily"]
    assert json.loads((tmp_path / "state.json").read_text("utf-8"))["digest_date"] == "2026-11-19"


def test_warning_pre_uses_the_pre_subscription_model_while_warning_uses_the_open_price_model_after_the_subscription():
    from ipo.main import _warning_pre
    from ipo.patterns import warning_level
    pred = {"prob": {"p_down": 0.359, "threshold": 0.35, "warn": True}, "open_down": {"p_down": 0.213, "threshold": 0.25, "warn": False}}
    patterns = [{"key": "x", "kind": "risk", "phase": "pre"}]
    assert warning_level(pred, patterns) is None                 # after the subscription: the open-price judgment: no warning
    assert _warning_pre(pred, patterns) == "strong"              # the earlier judgment: warns, and a pre pattern agrees
    assert _warning_pre({"prob": {"warn": True}}, []) == "warn"
    assert _warning_pre({"prob": {"warn": False}}, patterns) is None


def test_warning_pre_is_none_without_a_pre_model_or_prediction():
    from ipo.main import _warning_pre
    assert _warning_pre(None, []) is None
    assert _warning_pre({"open_down": {"warn": True}}, []) is None


def _fetch_with_broken_details(broken_nos=None):
    """The real table fixtures; every detail page is a maintenance page, or only those in broken_nos."""
    def fetch(url):
        if "o=v" in url and (broken_nos is None or any(url.endswith(f"no={n}") for n in broken_nos)):
            return "<html><body>점검 중입니다</body></html>"
        return fake_fetch(url)
    return fetch


def test_one_broken_detail_page_does_not_stop_the_run_and_is_reported(tmp_path):
    rec = Rec()
    assert run(tmp_path, Target(topic="t"), "https://s/", NOW, fetch=_fetch_with_broken_details({2336, 2352}), post=rec) == 0
    data = json.loads((tmp_path / "ipos.json").read_text("utf-8"))
    assert [f["no"] for f in data["detail_failures"]] == [2336, 2352]
    assert data["detail_failures"][0]["name"] == "넥스아이" and "anchor" in data["detail_failures"][0]["error"]
    assert "유캐스트" in [i["name"] for i in data["ipos"]]                       # the stock stays on the calendar with its table values
    alerts = [c for c in rec.calls if c["message"].startswith("일부 종목 정보가 갱신되지 않았어요")]
    assert [(c["title"], c["message"]) for c in alerts] == [("공모주 달력", "일부 종목 정보가 갱신되지 않았어요 · 넥스아이, 유캐스트")]


def test_no_failures_means_no_detail_failures_key_and_no_problem_alert(tmp_path):
    rec = Rec()
    run(tmp_path, Target(topic="t"), "https://s/", NOW, fetch=fake_fetch, post=rec)
    assert "detail_failures" not in json.loads((tmp_path / "ipos.json").read_text("utf-8"))
    assert not any("갱신되지 않았어요" in c["message"] for c in rec.calls)


def test_mostly_broken_detail_pages_fail_the_run_and_keep_the_old_file(tmp_path):
    (tmp_path / "ipos.json").write_text('{"ipos":[{"no":1}]}', "utf-8")
    rec = Rec()
    assert run(tmp_path, Target(topic="t"), "https://s/", NOW, fetch=_fetch_with_broken_details(), post=rec) == 1
    assert json.loads((tmp_path / "ipos.json").read_text("utf-8"))["ipos"] == [{"no": 1}]
    assert (rec.calls[-1]["title"], rec.calls[-1]["message"]) == ("공모주 달력", "앱 정보가 최신이 아닐 수 있어요. 다음 갱신 때 다시 시도해요.")   # no error text on the phone


def test_quiet_hours_keep_problem_alerts_in_the_payload_and_logs(tmp_path, monkeypatch, capsys):
    from ipo import main

    def boom(*args, **kwargs):
        raise RuntimeError("ledger broke")

    monkeypatch.setattr(main, "record_predictions", boom)
    rec = Rec()
    fetch = _fetch_with_broken_details({2336})
    assert run(tmp_path, Target(topic="t"), "", NOW.replace(hour=3), fetch=fetch, post=rec) == 0
    data = json.loads((tmp_path / "ipos.json").read_text("utf-8"))
    assert data["detail_failures"][0]["no"] == 2336
    assert "ledger broke" in data["ledger_error"]
    assert "detail failure 2336" in capsys.readouterr().out
    assert rec.calls == []
    assert not (tmp_path / "state.json").exists()


def test_a_failed_problem_alert_is_only_logged(tmp_path):
    def boom(url, json, timeout):
        raise RuntimeError("ntfy down")
    assert run(tmp_path, Target(topic="t"), "https://s/", NOW, fetch=_fetch_with_broken_details({2352}), post=boom) == 0


def test_a_ledger_failure_is_reported_in_the_payload_and_by_an_alert_but_the_run_goes_on(tmp_path, monkeypatch):
    import ipo.main as main

    def boom(*a, **k):
        raise RuntimeError("ledger broke")
    monkeypatch.setattr(main, "record_predictions", boom)
    rec = Rec()
    assert run(tmp_path, Target(topic="t"), "https://s/", NOW, fetch=fake_fetch, post=rec) == 0
    data = json.loads((tmp_path / "ipos.json").read_text("utf-8"))
    assert "ledger broke" in data["ledger_error"] and data["ledger"] is None
    alerts = [c for c in rec.calls if c["message"].startswith("실전 성적")]
    assert [(c["title"], c["message"]) for c in alerts] == [("공모주 달력", "실전 성적을 갱신하지 못했어요")]   # the error text stays out of the alert


def _daily_run(tmp_path, ipos, when, post):
    from ipo.main import _send_alerts
    _send_alerts(tmp_path, ipos, Target(topic="t"), "https://s/", when, post)


def _state(tmp_path):
    return json.loads((tmp_path / "state.json").read_text("utf-8"))


def test_the_daily_alert_is_three_counts_with_the_front_page_as_its_click(tmp_path):     # (a)
    calls, post = _calls()
    clean = _digest_ipo(1, name="가나다", sub_start="2026-11-24", sub_end="2026-11-26")
    warn = _digest_ipo(2, name="라마바", sub_start="2026-11-25", sub_end="2026-11-26", warning="warn")
    today_sub = _digest_ipo(3, name="사아자", sub_start="2026-11-23", sub_end="2026-11-24", warning="strong")
    today_listing = _digest_ipo(4, name="차카타", sub_start="2026-11-10", sub_end="2026-11-11", listing_date="2026-11-23")
    (tmp_path / "state.json").write_text(json.dumps({"sent": ["result:3", "result:4"]}), "utf-8")   # 3 and 4 were announced before
    _daily_run(tmp_path, [clean, warn, today_sub, today_listing], datetime(2026, 11, 23, 8, 17, tzinfo=KST), post)
    assert [(c["title"], c["message"], c["click"]) for c in calls] == [
        ("공모주 달력", NL.join(["수요예측 : 2건", "청약 시작 : 1건", "오늘 상장 : 1건"]), "https://s/")]
    assert {"result:1", "result:2"} <= set(_state(tmp_path)["sent"]) and _state(tmp_path)["digest_date"] == "2026-11-23"


def test_a_day_with_nothing_still_sends_all_three_lines(tmp_path):                             # (b)
    calls, post = _calls()
    _daily_run(tmp_path, [], datetime(2026, 11, 21, 8, 17, tzinfo=KST), post)
    assert [(c["title"], c["message"], c["click"]) for c in calls] == [
        ("공모주 달력", NL.join(["수요예측 : 0건", "청약 시작 : 0건", "오늘 상장 : 0건"]), "https://s/")]


def test_a_first_run_at_18_still_sends_the_daily_alert_and_a_second_run_does_not(tmp_path):    # (c)
    calls, post = _calls()
    evening = datetime(2026, 11, 19, 18, 0, tzinfo=KST)
    _daily_run(tmp_path, [], evening, post)
    _daily_run(tmp_path, [], evening.replace(hour=19), post)
    assert _kinds(calls) == ["daily"]


def test_a_failed_daily_send_records_nothing_and_the_next_run_of_the_day_sends_it(tmp_path):    # (d)
    ipo = _digest_ipo(3)
    attempts = []

    def boom(url, json, timeout):
        attempts.append(json["title"])
        raise RuntimeError("ntfy down")
    _daily_run(tmp_path, [ipo], datetime(2026, 11, 19, 8, 17, tzinfo=KST), boom)
    assert attempts == ["공모주 달력"]                                      # the send was really tried
    state = _state(tmp_path) if (tmp_path / "state.json").exists() else {"sent": []}
    assert "digest_date" not in state and "result:3" not in state["sent"]
    calls, post = _calls()
    _daily_run(tmp_path, [ipo], datetime(2026, 11, 19, 12, 0, tzinfo=KST), post)
    state = _state(tmp_path)
    assert _kinds(calls) == ["daily"] and calls[0]["message"].split(chr(10))[0] == "수요예측 : 1건"
    assert state["digest_date"] == "2026-11-19" and "result:3" in state["sent"]


def test_a_result_that_went_out_urgently_at_0559_is_not_repeated_in_the_daily_alert(tmp_path):  # (e)
    calls, post = _calls()
    urgent = _digest_ipo(5, sub_start="2026-11-20", sub_end="2026-11-21")
    _daily_run(tmp_path, [urgent], datetime(2026, 11, 19, 5, 59, tzinfo=KST), post)
    assert _kinds(calls) == ["result"]
    _daily_run(tmp_path, [urgent], datetime(2026, 11, 19, 8, 17, tzinfo=KST), post)
    assert _kinds(calls) == ["result", "daily"]
    assert calls[1]["message"] == NL.join(["수요예측 : 0건", "청약 시작 : 0건", "오늘 상장 : 0건"])   # sub_start 11/20 is not today; the result was sent at 05:59


def test_the_daily_alert_counts_only_the_first_day_of_a_subscription_and_leaves_out_spacs_and_withdrawn(tmp_path):   # (f)
    calls, post = _calls()
    first_day = dict(sub_start="2026-11-23", sub_end="2026-11-24")
    waiting = _digest_ipo(1, name="결과없음", inst_competition=None, **first_day)      # counts: its subscription starts today
    running = _digest_ipo(5, name="진행중", sub_start="2026-11-22", sub_end="2026-11-24")   # in the middle of its period: not counted
    spac = _digest_ipo(2, name="스팩", is_spac=True, **first_day)
    gone = _digest_ipo(3, name="철회", withdrawn=True, **first_day)
    listing_spac = _digest_ipo(4, name="스팩상장", is_spac=True, listing_date="2026-11-23")
    _daily_run(tmp_path, [waiting, running, spac, gone, listing_spac], datetime(2026, 11, 23, 8, 17, tzinfo=KST), post)
    assert calls[0]["message"].split(NL) == ["수요예측 : 1건", "청약 시작 : 1건", "오늘 상장 : 0건"]   # only 진행중 has a result to send (결과없음 has none)


def test_a_stock_without_a_result_sorts_after_stocks_with_a_verdict_even_with_a_warning_set():   # (g)
    from ipo.notify import _verdict
    no_result = _digest_ipo(6, inst_competition=None, warning="strong")
    assert _verdict(no_result) == (3, "대기 중")
    assert _verdict(_digest_ipo(7)) < _verdict(no_result)


def _fail(no, name):
    return {"no": no, "name": name, "error": "x"}


def test_failure_message_names_up_to_three_stocks_then_counts_the_rest():
    from ipo.main import _failure_message
    head = "일부 종목 정보가 갱신되지 않았어요 · "
    assert _failure_message([_fail(1, "가"), _fail(2, "나"), _fail(3, "다")]) == head + "가, 나, 다"          # (1) three or fewer
    assert _failure_message([_fail(i, n) for i, n in enumerate("가나다라마", 1)]) == head + "가, 나, 다 외 2건"   # (2) five: first three + 2 more
    assert _failure_message([_fail(0, "data/ipos.json")]) == "이전 데이터를 읽지 못했어요"                          # (3) only a file failure
    assert _failure_message([_fail(1, "가"), _fail(2, "나"), _fail(5, "?")]) == head + "가, 나 외 1건"              # (4) named and unnamed mixed
    assert _failure_message([_fail(1, "가"), _fail(1, "가"), _fail(2, "나")]) == head + "가, 나"                    # (5) the same name once, first-seen order


def test_unnamed_failures_never_put_a_file_name_or_a_question_mark_on_the_phone():
    from ipo.main import _failure_message
    text = _failure_message([_fail(0, "data/ipos.json"), _fail(7, "?"), _fail(8, "가")])
    assert text == "일부 종목 정보가 갱신되지 않았어요 · 가 외 2건" and "ipos.json" not in text and "?" not in text


def test_the_ledger_alert_goes_out_once_a_day_and_a_failed_send_is_not_recorded(tmp_path):
    from ipo.main import _problem_alerts
    calls, post = _calls()
    day1, day2 = datetime(2026, 11, 20, 8, 17, tzinfo=KST), datetime(2026, 11, 20, 17, 47, tzinfo=KST)
    _problem_alerts(Target(topic="t"), [], ["boom"], post, tmp_path, day1)
    _problem_alerts(Target(topic="t"), [], ["boom"], post, tmp_path, day2)
    assert [c["message"] for c in calls] == ["실전 성적을 갱신하지 못했어요"]                       # same day twice: once
    assert _state(tmp_path)["ledger_alert_date"] == "2026-11-20"
    _problem_alerts(Target(topic="t"), [], ["boom"], post, tmp_path, datetime(2026, 11, 21, 8, 17, tzinfo=KST))
    assert [c["message"] for c in calls] == ["실전 성적을 갱신하지 못했어요"] * 2                   # next day: again

    def boom(url, json, timeout):
        raise RuntimeError("ntfy down")
    _problem_alerts(Target(topic="t"), [], ["boom"], boom, tmp_path, datetime(2026, 11, 22, 8, 17, tzinfo=KST))
    assert _state(tmp_path)["ledger_alert_date"] == "2026-11-21"                                  # the failed send recorded nothing
    _problem_alerts(Target(topic="t"), [], ["boom"], post, tmp_path, datetime(2026, 11, 22, 17, 47, tzinfo=KST))
    assert len(calls) == 3                                                                         # so the next run sends it


def test_the_detail_failure_alert_goes_out_every_run(tmp_path):
    from ipo.main import _problem_alerts
    calls, post = _calls()
    for hour in (8, 17):
        _problem_alerts(Target(topic="t"), [_fail(1, "가")], [], post, tmp_path, datetime(2026, 11, 20, hour, 0, tzinfo=KST))
    assert [c["message"] for c in calls] == ["일부 종목 정보가 갱신되지 않았어요 · 가"] * 2


def test_every_detail_failure_is_printed_to_the_log(tmp_path, capsys):
    run(tmp_path, Target(topic="t"), "https://s/", NOW, fetch=_fetch_with_broken_details({2336}), post=Rec())
    out = capsys.readouterr().out
    assert any(l.startswith("detail failure 2336 넥스아이: ") for l in out.splitlines())
