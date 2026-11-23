import json
from datetime import datetime

from ipo.config import KST
from ipo.ledger import fill_results, record_predictions, summarize
from ipo.main import run
from ipo.notify import Target
from ipo.models import Ipo
from tests.helpers import BARE_DETAIL
from tests.test_main import NOW, Rec, fake_fetch

GONE = "<script>alert('해당 정보가 없습니다.');</script>"
PREV = {"no": 9001, "name": "철회주", "url": "u", "sub_start": "2026-11-23", "sub_end": "2026-11-24", "listing_date": "2026-12-02",
        "inst_competition": None, "warning": "warn", "first_close": None}


def _write_previous(tmp_path, *extra):
    (tmp_path / "ipos.json").write_text(json.dumps({"ipos": [PREV, *extra]}), "utf-8")


def _fetch(page_for_9001, seen=None):
    def fetch(url):
        if url.endswith("no=9001"):
            if seen is not None:
                seen.append(url)
            return page_for_9001
        return fake_fetch(url)
    return fetch


def _ipos(tmp_path):
    return {i["no"]: i for i in json.loads((tmp_path / "ipos.json").read_text("utf-8"))["ipos"]}


def test_a_stock_that_vanished_and_whose_page_is_gone_is_carried_as_withdrawn_with_one_alert(tmp_path):
    _write_previous(tmp_path)
    rec = Rec()
    assert run(tmp_path, Target(topic="t"), "https://s/", NOW, fetch=_fetch(GONE), post=rec) == 0
    kept = _ipos(tmp_path)[9001]
    assert kept["withdrawn"] == "2026-11-17" and kept["warning"] is None
    alerts = [c for c in rec.calls if c["message"].startswith("청약 철회 · ")]
    assert [(c["title"], c["message"]) for c in alerts] == [("공모주 달력", "청약 철회 · 철회주 · 11/23~24")]
    state = json.loads((tmp_path / "state.json").read_text("utf-8"))
    assert "withdrawn:9001" in state["sent"]


def test_an_already_withdrawn_stock_is_carried_without_a_new_fetch_or_alert(tmp_path):
    _write_previous(tmp_path)
    run(tmp_path, Target(topic="t"), "https://s/", NOW, fetch=_fetch(GONE), post=Rec())
    seen, rec = [], Rec()
    assert run(tmp_path, Target(topic="t"), "https://s/", NOW, fetch=_fetch(GONE, seen), post=rec) == 0
    assert seen == [] and _ipos(tmp_path)[9001]["withdrawn"] == "2026-11-17"
    assert not any(c["message"].startswith("청약 철회 · ") for c in rec.calls)


def test_a_vanished_stock_whose_page_still_exists_is_a_failure_not_a_withdrawal(tmp_path):
    _write_previous(tmp_path)
    rec = Rec()
    assert run(tmp_path, Target(topic="t"), "https://s/", NOW, fetch=_fetch(BARE_DETAIL), post=rec) == 0
    data = json.loads((tmp_path / "ipos.json").read_text("utf-8"))
    kept = {i["no"]: i for i in data["ipos"]}[9001]
    assert kept["withdrawn"] is None                         # kept as it was, to be checked again
    assert any(f["no"] == 9001 and f["error"] == "목록에서 사라짐" for f in data["detail_failures"])
    assert any(c["message"].startswith("일부 종목 정보가 갱신되지 않았어요 · ") for c in rec.calls)


def test_a_failed_fetch_of_the_vanished_stock_is_a_failure_too(tmp_path):
    from ipo.fetch import FetchError
    _write_previous(tmp_path)

    def fetch(url):
        if url.endswith("no=9001"):
            raise FetchError("timeout")
        return fake_fetch(url)
    assert run(tmp_path, None, "", NOW, fetch=fetch, post=Rec()) == 0
    data = json.loads((tmp_path / "ipos.json").read_text("utf-8"))
    assert [f["no"] for f in data["detail_failures"]] == [9001]
    assert {i["no"]: i for i in data["ipos"]}[9001]["withdrawn"] is None   # not dropped: one timeout must not erase a stock


def test_a_stock_that_failed_the_check_is_fetched_again_next_run(tmp_path):
    from ipo.fetch import FetchError
    _write_previous(tmp_path)
    seen = []

    def flaky(url):
        if url.endswith("no=9001"):
            seen.append(url)
            if len(seen) == 1:
                raise FetchError("timeout")
            return GONE
        return fake_fetch(url)
    run(tmp_path, None, "", NOW, fetch=flaky, post=Rec())
    run(tmp_path, None, "", NOW, fetch=flaky, post=Rec())
    assert len(seen) == 2 and _ipos(tmp_path)[9001]["withdrawn"] == "2026-11-17"


def test_more_than_three_vanishing_at_once_is_a_site_problem_nothing_is_opened_or_marked(tmp_path):
    _write_previous(tmp_path, *({**PREV, "no": 9001 + k} for k in range(1, 4)))      # 9001..9004: four
    seen = []

    def fetch(url):
        if any(url.endswith(f"no={n}") for n in range(9001, 9005)):
            seen.append(url)
            return GONE
        return fake_fetch(url)
    assert run(tmp_path, None, "", NOW, fetch=fetch, post=Rec()) == 0
    data = json.loads((tmp_path / "ipos.json").read_text("utf-8"))
    assert seen == []
    kept = {i["no"]: i for i in data["ipos"]}
    assert all(kept[n]["withdrawn"] is None for n in range(9001, 9005))
    assert sorted(f["no"] for f in data["detail_failures"] if f["no"] >= 9001) == [9001, 9002, 9003, 9004]
    assert all("한꺼번에 사라짐(4개)" in f["error"] for f in data["detail_failures"] if f["no"] >= 9001)


def test_three_vanishing_at_once_are_still_checked(tmp_path):
    _write_previous(tmp_path, *({**PREV, "no": 9001 + k} for k in range(1, 3)))
    run(tmp_path, None, "", NOW, fetch=lambda url: GONE if any(url.endswith(f"no={n}") for n in (9001, 9002, 9003)) else fake_fetch(url), post=Rec())
    kept = _ipos(tmp_path)
    assert all(kept[n]["withdrawn"] == "2026-11-17" for n in (9001, 9002, 9003))


def test_withdrawing_clears_the_prediction_and_patterns(tmp_path):
    _write_previous(tmp_path)
    prev = json.loads((tmp_path / "ipos.json").read_text("utf-8"))
    prev["ipos"][0].update(prediction={"prob": {"p_down": 0.6}}, patterns=[{"name": "x"}], warning_pre="warn")
    (tmp_path / "ipos.json").write_text(json.dumps(prev), "utf-8")
    run(tmp_path, None, "", NOW, fetch=_fetch(GONE), post=Rec())
    kept = _ipos(tmp_path)[9001]
    assert kept["prediction"] is None and kept["patterns"] == [] and kept["warning_pre"] is None


def test_an_already_withdrawn_stock_before_the_cutoff_drops_without_a_fetch(tmp_path):
    old = {**PREV, "no": 9010, "sub_start": "2026-01-05", "sub_end": "2026-01-06", "listing_date": None, "withdrawn": "2026-01-04"}
    _write_previous(tmp_path, old)
    seen = []

    def fetch(url):
        seen.append(url)
        return GONE if url.endswith("no=9001") else fake_fetch(url)
    run(tmp_path, None, "", NOW, fetch=fetch, post=Rec())
    assert 9010 not in _ipos(tmp_path) and all("no=9010" not in u for u in seen)


def test_listed_or_long_gone_stocks_are_not_checked(tmp_path):
    listed = {**PREV, "no": 9002, "first_close": 5000}
    past = {**PREV, "no": 9003, "listing_date": "2026-11-01"}
    old = {**PREV, "no": 9004, "sub_start": "2026-01-05", "sub_end": "2026-01-06", "listing_date": None}
    _write_previous(tmp_path, listed, past, old)
    seen = []

    def fetch(url):
        if any(url.endswith(f"no={n}") for n in (9001, 9002, 9003, 9004)):
            seen.append(url)
            return GONE
        return fake_fetch(url)
    run(tmp_path, None, "", NOW, fetch=fetch, post=Rec())
    assert [u[-4:] for u in seen] == ["9001", "9004"]         # listed and already-past listing dates are skipped
    nos = set(_ipos(tmp_path))
    assert 9001 in nos and 9004 not in nos                   # the old withdrawn one is dropped by the calendar cutoff


def test_a_stock_that_is_listed_again_is_taken_from_the_new_collection(tmp_path):
    again = {**PREV, "no": 2352, "name": "유캐스트", "withdrawn": "2026-11-16", "warning": None}
    _write_previous(tmp_path, again)
    run(tmp_path, None, "", NOW, fetch=fake_fetch, post=Rec())
    assert "withdrawn" not in _ipos(tmp_path)[2352] or _ipos(tmp_path)[2352]["withdrawn"] is None


def test_a_broken_previous_file_is_reported_once(tmp_path):
    (tmp_path / "ipos.json").write_text("{not json", "utf-8")
    assert run(tmp_path, None, "", NOW, fetch=fake_fetch, post=Rec()) == 0
    data = json.loads((tmp_path / "ipos.json").read_text("utf-8"))
    bad = [f for f in data["detail_failures"] if f["name"] == "data/ipos.json"]
    assert len(bad) == 1 and bad[0]["no"] == 0


def test_a_missing_previous_file_is_silent(tmp_path):
    assert run(tmp_path, None, "", NOW, fetch=fake_fetch, post=Rec()) == 0
    assert not any(f["no"] == 0 for f in json.loads((tmp_path / "ipos.json").read_text("utf-8")).get("detail_failures", []))


def test_one_broken_row_is_skipped_and_reported_the_other_withdrawn_stock_survives(tmp_path):
    broken = {"no": 9005, "name": "깨진행"}                                   # required fields missing
    _write_previous(tmp_path, broken)
    run(tmp_path, None, "", NOW, fetch=_fetch(GONE), post=Rec())
    data = json.loads((tmp_path / "ipos.json").read_text("utf-8"))
    assert {i["no"]: i for i in data["ipos"]}[9001]["withdrawn"] == "2026-11-17"
    assert [f for f in data["detail_failures"] if f["no"] == 9005 and f["error"] == "이전 데이터 읽기 실패"]


def test_a_failed_withdrawal_alert_is_retried_next_run(tmp_path):
    _write_previous(tmp_path)

    def boom(url, json, timeout):
        raise RuntimeError("ntfy down")
    run(tmp_path, Target(topic="t"), "https://s/", NOW, fetch=_fetch(GONE), post=boom)
    assert "withdrawn:9001" not in json.loads((tmp_path / "state.json").read_text("utf-8")).get("sent", [])
    rec = Rec()
    run(tmp_path, Target(topic="t"), "https://s/", NOW, fetch=_fetch(GONE), post=rec)
    assert len([c for c in rec.calls if c["message"].startswith("청약 철회 · ")]) == 1


def _stock(**kw):
    base = dict(no=1, name="a", url="", sub_start="2026-11-23", sub_end="2026-11-24", listing_date="2026-12-02",
                prediction={"prob": {"p_down": 0.5, "warn": True, "threshold": 0.35}}, patterns=[])
    return Ipo(**{**base, **kw})


def test_the_ledger_does_not_record_a_withdrawn_stock_and_drops_one_already_recorded_from_the_counts():
    now = datetime(2026, 11, 21, 10, tzinfo=KST)
    ledger = {}
    assert record_predictions(ledger, [_stock(withdrawn="2026-11-21")], now, "m") == 0 and ledger == {}
    assert record_predictions(ledger, [_stock()], now, "m") == 1 and summarize(ledger)["pre"]["pending"] == 1
    fill_results(ledger, [_stock(withdrawn="2026-11-22")], now)
    assert ledger["1"]["withdrawn"] == "2026-11-22" and ledger["1"]["result"] is None
    pre = summarize(ledger)["pre"]
    assert (pre["saved"], pre["pending"]) == (0, 0)
    fill_results(ledger, [_stock()], now)                                          # it came back
    assert "withdrawn" not in ledger["1"] and summarize(ledger)["pre"]["pending"] == 1


def test_a_withdrawn_stock_gets_no_result_eve_or_pre_alert():
    from ipo.notify import due_alerts
    now = datetime(2026, 11, 22, 18, tzinfo=KST)
    live = _stock(inst_competition=300.0, sub_start="2026-11-23", sub_end="2026-11-24")
    assert due_alerts([live], {"sent": []}, now)                                   # a normal stock does get one
    assert due_alerts([_stock(inst_competition=300.0, sub_start="2026-11-23", sub_end="2026-11-24", withdrawn="2026-11-21")], {"sent": []}, now) == []


LATE = {**PREV, "listing_date": "2026-11-10", "sub_start": "2026-11-03", "sub_end": "2026-11-04"}   # NOW is 2026-11-17


def _seed_history(tmp_path, *nos):
    from ipo.history import save_history
    save_history(tmp_path / "history.json", [Ipo(no=n, name=f"h{n}", url="", listing_date="2026-11-10", final_price=10000,
                                                  open_price=12000, first_close=13000) for n in nos])


def test_a_kept_stock_whose_listing_day_passed_takes_its_result_from_the_history(tmp_path):
    (tmp_path / "ipos.json").write_text(json.dumps({"ipos": [LATE]}), "utf-8")
    _seed_history(tmp_path, 9001)
    seen = []
    assert run(tmp_path, None, "", NOW, fetch=_fetch(GONE, seen), post=Rec()) == 0
    data = json.loads((tmp_path / "ipos.json").read_text("utf-8"))
    kept = {i["no"]: i for i in data["ipos"]}[9001]
    assert (kept["first_close"], kept["open_price"], kept["withdrawn"]) == (13000, 12000, None)
    assert seen == [] and not [f for f in data.get("detail_failures", []) if f["no"] == 9001]


def test_a_kept_stock_whose_listing_day_passed_without_any_result_is_reported_once_and_dropped(tmp_path):
    (tmp_path / "ipos.json").write_text(json.dumps({"ipos": [LATE]}), "utf-8")
    for n in range(2):
        run(tmp_path, None, "", NOW, fetch=_fetch(GONE), post=Rec())
        data = json.loads((tmp_path / "ipos.json").read_text("utf-8"))
        assert 9001 not in {i["no"] for i in data["ipos"]}
        errs = [f["error"] for f in data.get("detail_failures", []) if f["no"] == 9001]
        assert errs == (["상장일이 지났는데 결과 없음"] if n == 0 else [])


def test_a_withdrawn_stock_stays_after_its_planned_listing_day_while_inside_the_cutoff(tmp_path):
    (tmp_path / "ipos.json").write_text(json.dumps({"ipos": [{**LATE, "withdrawn": "2026-11-05"}]}), "utf-8")
    seen = []
    run(tmp_path, None, "", NOW, fetch=_fetch(GONE, seen), post=Rec())
    assert _ipos(tmp_path)[9001]["withdrawn"] == "2026-11-05" and seen == []


def _opened(tmp_path, rows):
    (tmp_path / "ipos.json").write_text(json.dumps({"ipos": rows}), "utf-8")
    seen = []

    def fetch(url):
        for r in rows:
            if url.endswith(f"no={r['no']}"):
                seen.append(r["no"])
                return GONE
        return fake_fetch(url)
    run(tmp_path, None, "", NOW, fetch=fetch, post=Rec())
    return seen


def test_already_withdrawn_stocks_do_not_count_toward_the_mass_limit(tmp_path):
    done = [{**PREV, "no": 9100 + k, "withdrawn": "2026-11-10"} for k in range(3)]
    new = [{**PREV, "no": 9200 + k} for k in range(2)]
    assert sorted(_opened(tmp_path, done + new)) == [9200, 9201]
    assert all(_ipos(tmp_path)[n]["withdrawn"] == "2026-11-17" for n in (9200, 9201))


def test_late_stocks_do_not_count_toward_the_mass_limit(tmp_path):
    late = [{**LATE, "no": 9300 + k} for k in range(4)]
    new = {**PREV, "no": 9400}
    assert _opened(tmp_path, late + [new]) == [9400]
    assert _ipos(tmp_path)[9400]["withdrawn"] == "2026-11-17"


def test_failures_with_no_zero_and_different_names_are_not_merged(tmp_path):
    (tmp_path / "ipos.json").write_text(json.dumps({"ipos": [{"no": 0, "name": "가"}, {"no": 0, "name": "나"}]}), "utf-8")
    run(tmp_path, None, "", NOW, fetch=fake_fetch, post=Rec())
    names = [f["name"] for f in json.loads((tmp_path / "ipos.json").read_text("utf-8"))["detail_failures"] if f["no"] == 0]
    assert sorted(names) == ["가", "나"]


def test_a_withdrawal_alert_for_a_stock_without_subscription_dates_has_only_the_name(tmp_path):
    from ipo.main import _withdrawn_alerts
    from ipo.models import Ipo
    rec = Rec()
    gone = Ipo(no=9002, name="철회주", url="u", withdrawn="2026-11-17")    # no subscription dates
    _withdrawn_alerts(tmp_path, [gone], Target(topic="t"), rec)
    assert [(c["title"], c["message"]) for c in rec.calls] == [("공모주 달력", "청약 철회 · 철회주")]
