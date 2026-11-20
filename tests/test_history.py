import json

from ipo.history import build_history, load_history, save_history, signal_backtest, update_history
from ipo.models import Ipo
from tests.helpers import BARE_DETAIL, load

PAGES = {
    "o=nw": load("listing"),
    "no=2336": load("detail_2336"),
    "no=2352": load("detail_2352"),
}


def fake_fetch(url):
    for key, html in PAGES.items():
        if key in url:
            return html
    return BARE_DETAIL


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


LISTING = "https://www.38.co.kr/html/fund/index.htm?o=nw"


def test_a_broken_detail_page_skips_only_that_stock_in_update_and_build():
    broken = "<html><body>점검 중</body></html>"
    fetch = lambda u: broken if u.endswith("no=2336") else fake_fetch(u)
    for run in (lambda f: update_history([], fetch=fetch, failures=f), lambda f: build_history(1, fetch=fetch, failures=f)):
        failures = []
        out = run(failures)
        assert 2336 not in {i.no for i in out} and len(out) > 5
        assert [f["no"] for f in failures] == [2336] and "anchor" in failures[0]["error"]


def test_too_many_broken_detail_pages_fail_history_collection():
    import pytest
    from ipo.parse import ParseError
    with pytest.raises(ParseError):
        update_history([], fetch=lambda u: "<html><body>점검 중</body></html>" if "o=v" in u else fake_fetch(u), failures=[])


def test_listing_rows_without_a_first_close_are_normal_in_small_numbers_but_an_error_when_most_are_missing():
    import pytest
    from ipo.parse import ParseError
    page = load("listing")
    assert len(build_history(1, fetch=fake_fetch)) > 0                    # the real page has ~25% such rows
    rows = "".join(f'<tr><td><a href="./?o=v&no={n}">종목{n}</a></td><td>2026/11/0{n % 9 + 1}</td>' + "<td>8,000</td>" * 6 + "<td>-</td></tr>" for n in range(1, 11))
    with pytest.raises(ParseError):
        build_history(1, fetch=lambda u: f"<table>{rows}</table>" if "o=nw" in u else fake_fetch(u))


def _listing_page(nos):
    rows = "".join(
        f'<tr><td><a href="./?o=v&no={n}">종목{n}</a></td><td>2026/11/01</td><td>1</td><td>1</td><td>8,000</td><td>1</td><td>9,000</td><td>1</td><td>10,000</td></tr>'
        for n in nos)
    return f"<table>{rows}</table>"


def test_update_history_reads_the_next_page_when_the_first_has_only_new_stocks_and_stops_at_a_known_one():
    pages = {1: _listing_page([30, 31]), 2: _listing_page([20, 21]), 3: _listing_page([10, 11])}
    seen = []

    def fetch(url):
        if "o=nw" in url:
            page = int(url.rsplit("page=", 1)[1])
            seen.append(page)
            return pages[page]
        return BARE_DETAIL
    known = [Ipo(no=21, name="종목21", url="", first_close=10000, listing_date="2026-11-01")]
    out = update_history(known, fetch=fetch)
    assert seen == [1, 2]                                         # page 2 has the known no 21: stop there
    assert {i.no for i in out} == {30, 31, 20, 21}


def test_update_history_stops_at_the_page_limit():
    from ipo.history import MAX_UPDATE_PAGES
    seen = []

    def fetch(url):
        if "o=nw" in url:
            page = int(url.rsplit("page=", 1)[1])
            seen.append(page)
            return _listing_page([1000 + page * 10, 1001 + page * 10])
        return BARE_DETAIL
    update_history([], fetch=fetch)
    assert seen == list(range(1, MAX_UPDATE_PAGES + 1))
