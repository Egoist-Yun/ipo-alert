import json
from datetime import datetime

from ipo.config import KST
from ipo.ledger import fill_results, record_predictions, summarize
from ipo.main import run
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
    assert run(tmp_path, "t", "https://s/", NOW, fetch=_fetch(GONE), post=rec) == 0
    kept = _ipos(tmp_path)[9001]
    assert kept["withdrawn"] == "2026-11-17" and kept["warning"] is None
    alerts = [c for c in rec.calls if c["title"] == "공모주 청약 철회"]
    assert len(alerts) == 1 and alerts[0]["message"] == "철회주 · 청약 11/23~11/24 예정이었어요"
    state = json.loads((tmp_path / "state.json").read_text("utf-8"))
    assert "withdrawn:9001" in state["sent"]


def test_an_already_withdrawn_stock_is_carried_without_a_new_fetch_or_alert(tmp_path):
    _write_previous(tmp_path)
    run(tmp_path, "t", "https://s/", NOW, fetch=_fetch(GONE), post=Rec())
    seen, rec = [], Rec()
    assert run(tmp_path, "t", "https://s/", NOW, fetch=_fetch(GONE, seen), post=rec) == 0
    assert seen == [] and _ipos(tmp_path)[9001]["withdrawn"] == "2026-11-17"
    assert not any(c["title"] == "공모주 청약 철회" for c in rec.calls)


def test_a_vanished_stock_whose_page_still_exists_is_a_failure_not_a_withdrawal(tmp_path):
    _write_previous(tmp_path)
    rec = Rec()
    assert run(tmp_path, "t", "https://s/", NOW, fetch=_fetch(BARE_DETAIL), post=rec) == 0
    data = json.loads((tmp_path / "ipos.json").read_text("utf-8"))
    assert 9001 not in {i["no"] for i in data["ipos"]}
    assert any(f["no"] == 9001 and f["error"] == "목록에서 사라짐" for f in data["detail_failures"])
    assert any(c["title"] == "공모주 상세 수집 일부 실패" for c in rec.calls)


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


def test_a_broken_previous_file_is_ignored(tmp_path):
    (tmp_path / "ipos.json").write_text("{not json", "utf-8")
    assert run(tmp_path, None, "", NOW, fetch=fake_fetch, post=Rec()) == 0


def test_a_failed_withdrawal_alert_is_retried_next_run(tmp_path):
    _write_previous(tmp_path)

    def boom(url, json, timeout):
        raise RuntimeError("ntfy down")
    run(tmp_path, "t", "https://s/", NOW, fetch=_fetch(GONE), post=boom)
    assert "withdrawn:9001" not in json.loads((tmp_path / "state.json").read_text("utf-8")).get("sent", [])
    rec = Rec()
    run(tmp_path, "t", "https://s/", NOW, fetch=_fetch(GONE), post=rec)
    assert len([c for c in rec.calls if c["title"] == "공모주 청약 철회"]) == 1


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


def test_a_withdrawn_stock_gets_no_result_eve_or_pre_alert():
    from ipo.notify import due_alerts
    now = datetime(2026, 11, 22, 18, tzinfo=KST)
    live = _stock(inst_competition=300.0, sub_start="2026-11-23", sub_end="2026-11-24")
    assert due_alerts([live], {"sent": []}, now)                                   # a normal stock does get one
    assert due_alerts([_stock(inst_competition=300.0, sub_start="2026-11-23", sub_end="2026-11-24", withdrawn="2026-11-21")], {"sent": []}, now) == []
