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
    assert any("유캐스트" in c["title"] for c in rec.calls)
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
