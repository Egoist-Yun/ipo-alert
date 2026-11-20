import json
from datetime import datetime

from ipo.config import KST
from ipo.main import run
from tests.helpers import load

NOW = datetime(2026, 11, 17, 18, 0, tzinfo=KST)
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
    return "<html><body></body></html>"


class Rec:
    def __init__(self):
        self.calls = []

    def __call__(self, url, json, timeout):
        self.calls.append(json)


def test_run_writes_ipos_json_and_alerts_once(tmp_path):
    rec = Rec()
    assert run(tmp_path, "t", "https://s/", NOW, fetch=fake_fetch, post=rec) == 0
    data = json.loads((tmp_path / "ipos.json").read_text("utf-8"))
    names = [i["name"] for i in data["ipos"]]
    assert "유캐스트" in names
    assert data["updated_at"].startswith("2026-11-17T18:00")
    assert data["disclaimer"].startswith("투자 권유가 아닌")
    ucast = next(i for i in data["ipos"] if i["name"] == "유캐스트")
    assert ucast["flag_count"] >= 1 and ucast["prediction"] is not None
    digests = [c for c in rec.calls if c["title"].startswith("수요예측 결과")]
    assert len(digests) == 1 and "유캐스트" in digests[0]["message"]          # one digest, not one alert per stock
    assert not any("⚠" in c["title"] or "⚠" in c["message"] for c in rec.calls)
    state = json.loads((tmp_path / "state.json").read_text("utf-8"))
    assert state["digest_date"] == "2026-11-17" and any(k.startswith("result:") for k in state["sent"])
    assert (tmp_path / "history.json").exists() and (tmp_path / "state.json").exists()
    before = len(rec.calls)
    assert run(tmp_path, "t", "https://s/", NOW, fetch=fake_fetch, post=rec) == 0
    assert len(rec.calls) == before


def test_run_without_topic_sends_nothing(tmp_path):
    rec = Rec()
    assert run(tmp_path, None, "", NOW, fetch=fake_fetch, post=rec) == 0
    assert rec.calls == [] and (tmp_path / "ipos.json").exists()


def test_failure_keeps_old_file_and_alerts(tmp_path):
    (tmp_path / "ipos.json").write_text('{"ipos":[{"no":1}]}', "utf-8")
    rec = Rec()
    code = run(tmp_path, "t", "https://s/", NOW, fetch=lambda u: "<html></html>", post=rec)
    assert code != 0
    assert json.loads((tmp_path / "ipos.json").read_text("utf-8"))["ipos"] == [{"no": 1}]
    assert rec.calls[-1]["title"] == "공모주 수집 실패"


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
    assert run(tmp_path, "t", "https://s/", NOW, fetch=fake_fetch, post=boom) == 0
    state = json.loads((tmp_path / "state.json").read_text("utf-8")) if (tmp_path / "state.json").exists() else {"sent": []}
    assert not any(k.startswith(("result:", "eve:")) for k in state.get("sent", []))
    assert "digest_date" not in state
    rec = Rec()                                    # the next run (ntfy back) sends the same digest
    assert run(tmp_path, "t", "https://s/", NOW, fetch=fake_fetch, post=rec) == 0
    assert any(c["title"].startswith("수요예측 결과") for c in rec.calls)


def test_before_6am_only_the_urgent_result_goes_out_and_it_is_not_the_morning_digest(tmp_path):
    early = datetime(2026, 11, 17, 5, 59, tzinfo=KST)
    rec = Rec()
    assert run(tmp_path, "t", "https://s/", early, fetch=fake_fetch, post=rec) == 0
    # the fixture's stock subscribes tomorrow (11/18): its result cannot wait, so it goes out even before 06:00
    assert [c["title"] for c in rec.calls] == ["수요예측 결과 1건"] and "유캐스트" in rec.calls[0]["message"]
    state = json.loads((tmp_path / "state.json").read_text("utf-8"))
    assert "digest_date" not in state                          # an urgent send is not the day's digest
    assert run(tmp_path, "t", "https://s/", NOW, fetch=fake_fetch, post=rec) == 0
    assert [c["title"] for c in rec.calls] == ["수요예측 결과 1건", "내일 청약 1건"]   # 18:00: only the eve digest is new
    sent = len(rec.calls)
    assert run(tmp_path, "t", "https://s/", NOW, fetch=fake_fetch, post=rec) == 0
    assert len(rec.calls) == sent


def _digest_ipo(no, **kw):
    from dataclasses import replace
    from tests.test_notify import NEXI
    base = dict(no=no, name=f"종목{no}", sub_start="2026-11-25", sub_end="2026-11-26", flag_count=0, unknown_count=0,
                signals=[], prediction=None, warning=None)
    return replace(NEXI, **{**base, **kw})


def _calls():
    calls = []
    return calls, lambda url, json, timeout: calls.append(json)


def test_a_morning_run_without_results_still_records_the_digest_date_so_the_afternoon_waits(tmp_path):
    from ipo.main import _send_alerts
    calls, post = _calls()
    waiting = _digest_ipo(1, inst_competition=None)                      # no demand result yet
    _send_alerts(tmp_path, [waiting], "t", "https://s/", datetime(2026, 11, 19, 8, 17, tzinfo=KST), post)
    assert calls == []
    assert json.loads((tmp_path / "state.json").read_text("utf-8"))["digest_date"] == "2026-11-19"   # (a) nothing to send: still recorded
    late = _digest_ipo(1)                                                # the result arrives in the afternoon
    _send_alerts(tmp_path, [late], "t", "https://s/", datetime(2026, 11, 19, 17, 47, tzinfo=KST), post)
    assert [c["title"] for c in calls] == []                            # not today: it waits for tomorrow's morning
    _send_alerts(tmp_path, [late], "t", "https://s/", datetime(2026, 11, 20, 8, 17, tzinfo=KST), post)
    assert [c["title"] for c in calls] == ["수요예측 결과 1건"]


def test_an_urgent_result_still_goes_out_in_the_afternoon_after_an_empty_morning(tmp_path):
    from ipo.main import _send_alerts
    calls, post = _calls()
    _send_alerts(tmp_path, [], "t", "https://s/", datetime(2026, 11, 19, 8, 17, tzinfo=KST), post)
    urgent = _digest_ipo(2, sub_start="2026-11-20", sub_end="2026-11-21")   # subscribes tomorrow
    _send_alerts(tmp_path, [urgent], "t", "https://s/", datetime(2026, 11, 19, 17, 47, tzinfo=KST), post)
    assert "수요예측 결과 1건" in [c["title"] for c in calls]


def test_a_failed_morning_send_is_not_recorded_and_the_afternoon_run_tries_again(tmp_path):
    from ipo.main import _send_alerts
    ipo = _digest_ipo(3)

    def boom(url, json, timeout):
        raise RuntimeError("ntfy down")
    _send_alerts(tmp_path, [ipo], "t", "https://s/", datetime(2026, 11, 19, 8, 17, tzinfo=KST), boom)
    state = json.loads((tmp_path / "state.json").read_text("utf-8"))
    assert "digest_date" not in state and "result:3" not in state["sent"]                       # (b)
    calls, post = _calls()
    _send_alerts(tmp_path, [ipo], "t", "https://s/", datetime(2026, 11, 19, 17, 47, tzinfo=KST), post)
    assert [c["title"] for c in calls] == ["수요예측 결과 1건"]
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
