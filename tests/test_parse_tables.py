import pytest

from ipo.parse import ParseError, parse_demand, parse_listing, parse_schedule
from tests.helpers import load


def test_schedule_nexi():
    rows = {r["name"]: r for r in parse_schedule(load("schedule"))}
    r = rows["넥스아이"]
    assert r["no"] == 2336
    assert (r["sub_start"], r["sub_end"]) == ("2026-11-03", "2026-11-04")
    assert (r["band_low"], r["band_high"], r["final_price"]) == (10500, 13000, 8000)
    assert r["underwriters"] == ["한국투자증권"]


def test_schedule_missing_price_is_none():
    r = next(r for r in parse_schedule(load("schedule")) if r["name"] == "제논")
    assert r["final_price"] is None


def test_schedule_multiple_underwriters_split():
    r = next(r for r in parse_schedule(load("schedule")) if r["name"] == "태석광학")
    assert r["underwriters"] == ["신한투자증권", "대신증권"]


def test_demand_nexi_and_missing_lockup():
    rows = {r["name"]: r for r in parse_demand(load("demand"))}
    assert rows["넥스아이"]["inst_competition"] == 66.58
    assert rows["넥스아이"]["lockup_pct"] == 0.06
    assert rows["넥스아이"]["offer_amount_mil"] == 40000
    assert rows["엠비디"]["lockup_pct"] is None


def test_listing_nexi():
    r = next(r for r in parse_listing(load("listing")) if r["name"] == "넥스아이")
    assert r["no"] == 2336
    assert (r["listing_date"], r["open_price"], r["first_close"]) == ("2026-11-12", 7620, 4810)


def test_listing_not_yet_listed_has_none_prices():
    r = next(r for r in parse_listing(load("listing")) if r["name"] == "아델")
    assert r["first_close"] is None and r["open_price"] is None


def test_same_stock_with_suffix_name_has_same_no_in_all_tables():
    found = {}
    for table, fn in (("schedule", parse_schedule), ("demand", parse_demand), ("listing", parse_listing)):
        found[table] = {r["no"] for r in fn(load(table)) if r["name"].startswith("영광(구")}
    assert found["schedule"] == found["demand"] == found["listing"] == {2333}


def test_empty_table_raises():
    for fn in (parse_schedule, parse_demand, parse_listing):
        with pytest.raises(ParseError):
            fn("<html><body><table></table></body></html>")


def test_short_row_is_a_parse_error_not_index_error():
    short = '<table><tr><td><a href="./?o=v&no=1">x</a></td><td>2026.10.22</td><td>1</td></tr></table>'
    for fn in (parse_schedule, parse_demand, parse_listing):
        with pytest.raises(ParseError):
            fn(short)


def _listing_row(no, date):
    cells = [f'<td><a href="./?o=v&no={no}">종목{no}</a></td>', f"<td>{date}</td>"] + ["<td>1</td>"] * 7
    return "<tr>" + "".join(cells) + "</tr>"


def test_rows_raise_when_most_candidate_rows_are_dropped_silently():
    rows = [_listing_row(1, "2026/10/22")] + [_listing_row(n, "날짜없음") for n in range(2, 11)]   # 10 data-shaped rows, 1 adopted
    with pytest.raises(ParseError) as e:
        parse_listing("<table>" + "".join(rows) + "</table>")
    assert "only 1 of 10" in str(e.value)                              # adopted and candidate counts, exactly


def test_rows_accept_exactly_half_and_ignore_one_cell_link_rows():
    half = [_listing_row(n, "2026/10/22") for n in range(1, 6)] + [_listing_row(n, "날짜없음") for n in range(6, 11)]
    assert len(parse_listing("<table>" + "".join(half) + "</table>")) == 5
    sidebar = "".join(f'<tr><td><a href="./?o=v&no={n}">링크{n}</a></td></tr>' for n in range(100, 140))   # 40 navigation rows: not candidates
    assert len(parse_listing("<table>" + _listing_row(1, "2026/10/22") + sidebar + "</table>")) == 1


def test_real_fixture_pages_pass_the_row_loss_check():
    from tests.helpers import load
    assert len(parse_schedule(load("schedule"))) == 30
    assert len(parse_demand(load("demand"))) == 20 and len(parse_listing(load("listing"))) == 20


def _listing_page(good, bad):
    rows = [_listing_row(n, "2026/10/22") for n in range(good)] + [_listing_row(100 + n, "날짜없음") for n in range(bad)]
    return "<table>" + "".join(rows) + "</table>"


def test_row_loss_boundary_around_one_half():
    with pytest.raises(ParseError):
        parse_listing(_listing_page(3, 4))                      # 3 of 7: below half
    assert len(parse_listing(_listing_page(4, 3))) == 4          # 4 of 7: kept
    with pytest.raises(ParseError):
        parse_listing(_listing_page(4, 6))                      # 4 of 10: below half


def _wide_row(no, date, cols):
    cells = [f'<td><a href="./?o=v&no={no}">종목{no}</a></td>', f"<td>{date}</td>"] + ["<td>1</td>"] * (cols - 2)
    return "<tr>" + "".join(cells) + "</tr>"


def test_schedule_and_demand_also_raise_on_row_loss():
    sched = "<table>" + _wide_row(1, "2026.10.22 ~ 2026.10.23", 6) + "".join(_wide_row(10 + n, "날짜없음", 6) for n in range(9)) + "</table>"
    demand = "<table>" + _wide_row(1, "2026.10.22", 6) + "".join(_wide_row(10 + n, "날짜없음", 6) for n in range(9)) + "</table>"
    with pytest.raises(ParseError) as e1:
        parse_schedule(sched)
    with pytest.raises(ParseError) as e2:
        parse_demand(demand)
    assert "only 1 of 10" in str(e1.value) and "only 1 of 10" in str(e2.value)
