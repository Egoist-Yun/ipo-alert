import json

from ipo.history import build_history, load_history, save_history, signal_backtest, update_history
from ipo.models import Ipo
from tests.helpers import load

PAGES = {
    "o=nw": load("listing"),
    "no=2336": load("detail_2336"),
    "no=2352": load("detail_2352"),
}


def fake_fetch(url):
    for key, html in PAGES.items():
        if key in url:
            return html
    return "<html><body></body></html>"


def test_build_history_fills_listing_and_detail():
    hist = build_history(1, fetch=fake_fetch)
    nexi = next(i for i in hist if i.no == 2336)
    assert nexi.first_close == 4810 and nexi.below_band_pct == 48.15 and nexi.float_pct == 37.03
    assert all(not i.is_spac and i.first_close is not None for i in hist)
    assert len({i.no for i in hist}) == len(hist)


def test_update_history_adds_only_new():
    existing = [Ipo(no=2336, name="넥스아이", url="", first_close=4810, below_band_pct=99.0,
                    listing_date="2026-11-12", final_price=8000)]
    out = update_history(existing, fetch=fake_fetch)
    assert [i.no for i in out].count(2336) == 1
    assert next(i for i in out if i.no == 2336).below_band_pct == 99.0
    assert any(i.name == "옵토닉스" and i.first_close == 18170 for i in out)


def mk(no, *, flags4, down, date="2026-10-01"):
    if flags4:
        kw = dict(band_low=10000, band_high=12000, final_price=10000, inst_competition=50.0,
                  lockup_pct=0.1, below_band_pct=40.0, float_pct=None)
    else:
        kw = dict(band_low=10000, band_high=12000, final_price=12000, inst_competition=900.0,
                  lockup_pct=10.0, below_band_pct=5.0, float_pct=10.0)
    price = kw["final_price"]
    return Ipo(no=no, name=f"s{no}", url="", listing_date=date,
               first_close=int(price * (0.8 if down else 1.3)), **kw)


def test_signal_backtest_groups_by_flag_count():
    hist = [mk(1, flags4=True, down=True), mk(2, flags4=True, down=True)] + \
           [mk(i, flags4=False, down=False) for i in range(3, 7)]
    out = signal_backtest(hist)
    assert "| 4 | 2 | 100% |" in out
    assert "| 0 | 4 | 0% |" in out


def test_history_roundtrip(tmp_path):
    items = [Ipo(no=1, name="a", url="u", first_close=5, final_price=4, underwriters=["x"])]
    path = tmp_path / "h.json"
    save_history(path, items)
    assert load_history(path) == items
    assert json.loads(path.read_text("utf-8"))[0]["name"] == "a"
