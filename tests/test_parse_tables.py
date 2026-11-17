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
