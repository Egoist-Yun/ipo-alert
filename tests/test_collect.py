from dataclasses import replace

from ipo.collect import collect_current, market_mood
from ipo.models import Ipo
from tests.helpers import load

PAGES = {
    "https://www.38.co.kr/html/fund/index.htm?o=k": load("schedule"),
    "https://www.38.co.kr/html/fund/index.htm?o=r1": load("demand"),
    "https://www.38.co.kr/html/fund/index.htm?o=nw": load("listing"),
    "https://www.38.co.kr/html/fund/?o=v&no=2336": load("detail_2336"),
    "https://www.38.co.kr/html/fund/?o=v&no=2352": load("detail_2352"),
}


def fake_fetch(url):
    return PAGES.get(url, "<html><body></body></html>")


def test_collect_merges_tables_by_no():
    ipos = collect_current(fetch=fake_fetch, today="2026-11-17")
    nexi = [i for i in ipos if i.no == 2336]
    assert len(nexi) == 1
    n = nexi[0]
    assert (n.final_price, n.inst_competition, n.lockup_pct) == (8000, 66.58, 0.06)
    assert (n.listing_date, n.first_close) == ("2026-11-12", 4810)
    assert n.below_band_pct == 48.15 and n.market == "코스닥"
    assert n.is_bio is True and n.is_spac is False


def test_collect_marks_spac_and_skips_its_detail():
    seen = []
    ipos = collect_current(fetch=lambda u: (seen.append(u), fake_fetch(u))[1], today="2026-11-17")
    spac = next(i for i in ipos if "스팩" in i.name)
    assert spac.is_spac is True
    assert not any(f"no={spac.no}" in u and "o=v" in u for u in seen)


def test_collect_uses_cache_for_finished_stocks():
    cache = {}
    collect_current(fetch=fake_fetch, today="2026-11-17", cache=cache)
    assert 2336 in cache
    seen = []
    collect_current(fetch=lambda u: (seen.append(u), fake_fetch(u))[1], today="2026-11-17", cache=cache)
    assert "https://www.38.co.kr/html/fund/?o=v&no=2336" not in seen


def mk(i, ret, date):
    return Ipo(no=i, name=f"s{i}", url="", final_price=100, first_close=int(100 * (1 + ret)),
               listing_date=date)


def test_market_mood_none_when_fewer_than_10():
    hist = [mk(i, -0.1, f"2026-10-{i + 1:02d}") for i in range(9)]
    assert market_mood(hist, "2026-11-01") is None


def test_market_mood_ratio_of_latest_10_before_date():
    hist = [mk(i, -0.1 if i < 4 else 0.2, f"2026-10-{i + 1:02d}") for i in range(12)]
    # latest 10 before 11-01 are i=2..11 -> falling: i=2,3 -> 2 of 10
    assert market_mood(hist, "2026-11-01") == 0.2


def test_market_mood_ignores_spac_and_future():
    hist = [mk(i, -0.1, f"2026-10-{i + 1:02d}") for i in range(10)]
    hist[0] = replace(hist[0], is_spac=True)
    assert market_mood(hist, "2026-11-01") is None
    assert market_mood(hist + [mk(99, -0.1, "2026-12-01")], "2026-11-01") is None


def test_collect_raises_when_demand_columns_shifted():
    from ipo.parse import ParseError
    import pytest
    row = ('<table><tr><td><a href="./?o=v&no=1">x</a></td><td>2026.10.22</td><td>1~2</td><td>8,000</td>'
           '<td>40,000</td><td>n/a</td><td>0.06%</td><td>y</td></tr></table>')
    pages = {**PAGES, "https://www.38.co.kr/html/fund/index.htm?o=r1": row}
    with pytest.raises(ParseError):
        collect_current(fetch=lambda u: pages.get(u, "<html></html>"), today="2026-11-17")


def test_apply_detail_adds_the_subscription_facts_and_keeps_old_values_when_missing():
    from ipo.collect import apply_detail
    from ipo.parse import parse_detail
    full = parse_detail(load("detail_2352"))
    ipo = Ipo(no=2352, name="x", url="")
    apply_detail(ipo, full)
    assert (ipo.total_shares, ipo.retail_shares, ipo.retail_deposit_pct) == (800000, 200000, 50.0)
    assert ipo.refund_date == "2026-11-23" and (ipo.demand_start, ipo.demand_end) == ("2026-11-09", "2026-11-13")
    assert [b["name"] for b in ipo.brokers] == ["유진투자증권", "신영증권"]
    # a later page that lacks these values must not erase what was collected before
    empty = parse_detail("<html><body>종목명 X</body></html>")
    apply_detail(ipo, empty)
    assert ipo.total_shares == 800000 and ipo.refund_date == "2026-11-23" and len(ipo.brokers) == 2


def test_apply_detail_resets_retail_shares_high_when_the_range_becomes_a_single_value():
    from ipo.collect import apply_detail
    from ipo.parse import parse_detail
    ipo = Ipo(no=1, name="x", url="", retail_shares=542500, retail_shares_high=651000)
    fixed = parse_detail(load("detail_2352"))  # retail 200,000 (a single value)
    apply_detail(ipo, fixed)
    assert (ipo.retail_shares, ipo.retail_shares_high) == (200000, None)


def test_apply_detail_keeps_retail_shares_high_when_the_page_has_no_retail_value_at_all():
    from ipo.collect import apply_detail
    from ipo.parse import parse_detail
    ipo = Ipo(no=1, name="x", url="", retail_shares=542500, retail_shares_high=651000)
    apply_detail(ipo, parse_detail("<html><body>종목명 X</body></html>"))
    assert (ipo.retail_shares, ipo.retail_shares_high) == (542500, 651000)
