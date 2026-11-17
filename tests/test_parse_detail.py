from ipo.parse import parse_detail
from tests.helpers import load


def test_detail_nexi():
    d = parse_detail(load("detail_2336"))
    assert d["market"] == "코스닥"
    assert "의학" in d["industry"]
    assert (d["band_low"], d["band_high"], d["final_price"]) == (10500, 13000, 8000)
    assert (d["sub_start"], d["sub_end"]) == ("2026-11-03", "2026-11-04")
    assert d["listing_date"] == "2026-11-12"
    assert d["offer_amount_mil"] == 40000
    assert d["inst_competition"] == 66.58
    assert d["lockup_pct"] == 0.06
    assert d["below_band_pct"] == 48.15
    assert d["float_pct"] == 37.03


def test_detail_other_float_table_layout():
    d = parse_detail(load("detail_2352"))
    assert d["float_pct"] == 36.81
    assert d["listing_date"] == "2026-11-30"
    assert d["lockup_pct"] == 0.57


def test_detail_missing_sections_are_none():
    d = parse_detail("<html><body>종목명 X</body></html>")
    assert d["below_band_pct"] is None and d["float_pct"] is None
    assert d["market"] is None and d["final_price"] is None
