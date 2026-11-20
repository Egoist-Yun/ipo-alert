from dataclasses import replace

from ipo.collect import collect_current, market_mood
from ipo.models import Ipo
from tests.helpers import BARE_DETAIL, load

PAGES = {
    "https://www.38.co.kr/html/fund/index.htm?o=k": load("schedule"),
    "https://www.38.co.kr/html/fund/index.htm?o=r1": load("demand"),
    "https://www.38.co.kr/html/fund/index.htm?o=nw": load("listing"),
    "https://www.38.co.kr/html/fund/?o=v&no=2336": load("detail_2336"),
    "https://www.38.co.kr/html/fund/?o=v&no=2352": load("detail_2352"),
}


def fake_fetch(url):
    return PAGES.get(url, BARE_DETAIL)


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
    empty = parse_detail(BARE_DETAIL)
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
    apply_detail(ipo, parse_detail(BARE_DETAIL))
    assert (ipo.retail_shares, ipo.retail_shares_high) == (542500, 651000)


DETAIL = "https://www.38.co.kr/html/fund/?o=v&no="


def _broken_fetch(broken: set):
    """The real table fixtures, every detail page fine except the numbers in `broken`."""
    def fetch(url):
        if url.startswith(DETAIL) and int(url.rsplit("=", 1)[1]) in broken:
            return "<html><body>점검 중입니다</body></html>"
        return fake_fetch(url)
    return fetch


def test_one_broken_detail_page_is_skipped_reported_and_never_cached():
    cache, failures = {}, []
    ipos = collect_current(fetch=_broken_fetch({2352}), cache=cache, today="2026-11-17", failures=failures)
    assert [(f["no"], f["name"]) for f in failures] == [(2352, next(i.name for i in ipos if i.no == 2352))]
    assert "anchor" in failures[0]["error"]
    bad = next(i for i in ipos if i.no == 2352)
    assert bad.inst_competition is not None and bad.market is None      # the table values stay, no detail was applied
    assert 2352 not in cache and 2336 in cache                          # 2352 has a competition value: it would be cached if it were good


def test_a_fetch_error_on_one_detail_page_is_also_skipped():
    from ipo.fetch import FetchError

    def fetch(url):
        if url == DETAIL + "2352":
            raise FetchError(url + ": timeout")
        return fake_fetch(url)
    failures = []
    collect_current(fetch=fetch, today="2026-11-17", failures=failures)
    assert [f["no"] for f in failures] == [2352] and "timeout" in failures[0]["error"]


def test_other_exceptions_are_not_swallowed():
    import pytest

    def fetch(url):
        if url == DETAIL + "2352":
            raise ValueError("bug")
        return fake_fetch(url)
    with pytest.raises(ValueError):
        collect_current(fetch=fetch, today="2026-11-17")


def test_too_many_broken_detail_pages_fail_the_whole_collection_with_counts_and_names():
    import pytest
    from ipo.collect import MAX_DETAIL_FAIL_RATIO
    from ipo.parse import ParseError
    attempted = [int(u.rsplit("=", 1)[1]) for u in _seen_details()]
    limit = int(len(attempted) * MAX_DETAIL_FAIL_RATIO)               # the most failures that is still allowed
    collect_current(fetch=_broken_fetch(set(attempted[:limit])), today="2026-11-17", failures=[])
    with pytest.raises(ParseError) as e:
        collect_current(fetch=_broken_fetch(set(attempted[:limit + 1])), today="2026-11-17", failures=[])
    msg = str(e.value)
    assert f"{limit + 1} of {len(attempted)}" in msg


def _seen_details():
    seen = []
    collect_current(fetch=lambda u: (seen.append(u), fake_fetch(u))[1], today="2026-11-17")
    return [u for u in seen if u.startswith(DETAIL)]


def test_a_page_without_any_anchor_never_reaches_the_cache_even_when_everything_fails():
    import pytest
    from ipo.parse import ParseError
    cache = {}
    with pytest.raises(ParseError):
        collect_current(fetch=lambda u: "<html><body>점검</body></html>" if u.startswith(DETAIL) else fake_fetch(u), cache=cache, today="2026-11-17")
    assert cache == {}
