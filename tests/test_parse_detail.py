import pytest

from ipo.parse import ParseError, parse_detail
from tests.helpers import BARE_DETAIL, load


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


BARE = BARE_DETAIL  # a recognisable detail page (anchor label present) with nothing else on it


def test_detail_without_any_anchor_label_is_a_parse_error_naming_the_labels():
    for html in ("", "<html></html>", "<html><body>종목명 X</body></html>", "<html><body><table><tr><td>업종</td><td>x</td></tr></table></body></html>"):
        with pytest.raises(ParseError) as e:
            parse_detail(html)
        for label in ("시장구분", "공모청약일", "희망공모가액"):
            assert label in str(e.value)


def test_detail_whose_anchor_labels_have_empty_values_is_a_parse_error():
    page = ("<html><body><table><tr><td>시장구분</td><td></td></tr><tr><td>공모청약일</td><td> </td></tr>"
            "<tr><td>희망공모가액</td><td></td></tr></table></body></html>")
    with pytest.raises(ParseError):
        parse_detail(page)


def test_detail_with_only_one_anchor_label_is_accepted_and_the_rest_is_none():
    for label in ("시장구분", "공모청약일", "희망공모가액"):
        d = parse_detail(f"<html><body><table><tr><td>{label}</td><td>-</td></tr></table></body></html>")
        assert d["final_price"] is None and d["brokers"] == []


def test_detail_real_fixtures_pass_the_anchor_check():
    for name in ("detail_2336", "detail_2352"):
        assert parse_detail(load(name))["market"] == "코스닥"


def test_detail_missing_sections_are_none():
    d = parse_detail(BARE)
    assert d["below_band_pct"] is None and d["float_pct"] is None
    assert d["market"] is None and d["final_price"] is None


def test_detail_financials_and_offering_nexi():
    d = parse_detail(load("detail_2336"))
    assert d["revenue_mil"] == 5110 and d["net_income_mil"] == -52331
    assert d["capital_mil"] == 22922 and d["par_value"] == 500
    assert d["old_share_pct"] == 0.0
    assert d["inst_count"] == 506


def test_detail_new_fields_missing_are_none():
    d = parse_detail(BARE)
    for key in ("revenue_mil", "net_income_mil", "capital_mil", "par_value", "old_share_pct", "inst_count"):
        assert d[key] is None


def test_detail_old_share_from_secondary_offering_text():
    html = ("<html><body><table><tr><td>공모청약일</td><td>-</td></tr></table><table><tr><td>상장공모</td><td>신주모집 : 800,000 주 (80%) / 구주매출 : 200,000 주 (20%)</td>"
            "</tr></table></body></html>")
    assert parse_detail(html)["old_share_pct"] == 20.0


def test_detail_retail_competition_after_and_before_subscription():
    assert parse_detail(load("detail_2336"))["retail_competition"] == 13.26
    assert parse_detail(load("detail_2352"))["retail_competition"] is None


def test_detail_subscription_facts_ucast():
    d = parse_detail(load("detail_2352"))
    assert d["total_shares"] == 800000
    assert d["retail_shares"] == 200000
    assert d["retail_deposit_pct"] == 50.0  # the retail side, not the institutional 100%
    assert d["refund_date"] == "2026-11-23"
    assert (d["demand_start"], d["demand_end"]) == ("2026-11-09", "2026-11-13")
    assert d["brokers"] == [
        {"name": "유진투자증권", "shares": 160000, "limit_text": "16,000 ~ 20,000 주", "limit_max": 20000},
        {"name": "신영증권", "shares": 40000, "limit_text": "1,300 주", "limit_max": 1300},
    ]
    assert sum(b["shares"] for b in d["brokers"]) == d["retail_shares"]


def test_detail_subscription_facts_nexi_has_no_broker_table():
    d = parse_detail(load("detail_2336"))
    assert d["total_shares"] == 5000000 and d["retail_shares"] == 1250000
    assert d["retail_deposit_pct"] == 50.0
    assert d["refund_date"] == "2026-11-06"
    assert (d["demand_start"], d["demand_end"]) == ("2026-10-22", "2026-10-28")
    assert d["brokers"] == []


def test_detail_subscription_facts_missing_are_none_or_empty():
    d = parse_detail(BARE)
    for key in ("total_shares", "retail_shares", "retail_deposit_pct", "refund_date", "demand_start", "demand_end"):
        assert d[key] is None, key
    assert d["brokers"] == []


def test_detail_broker_limit_dash_means_no_limit_number():
    html = ("<html><body><table><tr><td>공모청약일</td><td>-</td></tr></table><table><tr><td>인수회사</td><td>주식수</td><td>청약한도</td><td>기타</td></tr>"
            "<tr><td>가증권</td><td>10,000 주</td><td>-</td><td>인수</td></tr></table></body></html>")
    assert parse_detail(html)["brokers"] == [{"name": "가증권", "shares": 10000, "limit_text": "-", "limit_max": None}]


def test_detail_retail_deposit_pct_when_the_retail_share_is_still_a_range():
    # before the offer is fixed the page shows 542,500~651,000 주 (25.0~30.0%) instead of one number
    html = ("<html><body><table><tr><td>공모청약일</td><td>-</td></tr></table><table><tr><td>일반청약자</td><td>542,500~651,000 주 \xa0(25.0~30.0%)</td>"
            "<td>청약증거금율 : 50%</td><td>청약 최고한도 : - 주</td></tr></table></body></html>")
    d = parse_detail(html)
    assert d["retail_deposit_pct"] == 50.0
    assert d["retail_shares"] == 542500
    assert d["retail_shares_high"] == 651000  # the upper end of the range


def test_detail_retail_deposit_pct_when_both_ends_of_the_range_carry_a_percent_sign():
    # the live page of an offer still being fixed: 550,000~660,000 주 (25.00%~30.00%)
    html = ("<html><body><table><tr><td>공모청약일</td><td>-</td></tr></table><table><tr><td>일반청약자</td><td>550,000~660,000 주 \xa0(25.00%~30.00%)</td>"
            "<td>청약증거금율 : 50%</td></tr></table></body></html>")
    assert parse_detail(html)["retail_deposit_pct"] == 50.0


def test_detail_retail_shares_high_is_none_for_a_single_value_and_when_missing():
    assert parse_detail(load("detail_2352"))["retail_shares_high"] is None
    assert parse_detail(load("detail_2336"))["retail_shares_high"] is None
    assert parse_detail(BARE)["retail_shares_high"] is None


def test_detail_retail_shares_range_in_a_plain_cell():
    html = "<html><body><table><tr><td>공모청약일</td><td>-</td></tr></table><table><tr><td>일반청약자</td><td>500,000~600,000 주  (25.00%~30.00%)</td></tr></table></body></html>"
    d = parse_detail(html)
    assert (d["retail_shares"], d["retail_shares_high"]) == (500000, 600000)


def _demand_page(*rows, band="19,000 ~ 23,000 원", float_row=None):
    """A minimal page: the band, a demand table with the given label rows, optionally a float table whose last row is float_row."""
    body = "".join(f"<tr><td>{label}</td><td>432</td><td>58,445,000</td><td>{pct}</td></tr>" for label, pct in rows)
    page = f"<html><body><table><tr><td>시장구분</td><td>코스닥</td></tr><tr><td>희망공모가액</td><td>{band}</td></tr></table><table>{body}</table>"
    if float_row:
        page += f"<table><tr><td>구분</td><td>유통가능</td></tr><tr><td>{float_row}</td><td>5,064,910</td><td>100.00%</td><td>63.19%</td><td>36.81%</td><td>-</td></tr></table>"
    return page + "</body></html>"


def test_below_band_pct_from_a_plain_price_row_equal_to_the_band_bottom_ucast():
    assert parse_detail(load("detail_2352"))["below_band_pct"] == 56.17
    assert parse_detail(load("detail_2336"))["below_band_pct"] == 48.15        # the "(하단) 미만" form still works


def test_below_band_pct_accepts_spacing_and_missing_won_sign_variants():
    for label in ("19,000원 미만", "19,000 원 미만", "19,000 미만", "19,000원 미만(하단미만)", "19,000원(하단) 미만"):
        assert parse_detail(_demand_page((label, "12.50%")))["below_band_pct"] == 12.5, label


def test_below_band_pct_ignores_range_rows_and_prices_other_than_the_band_bottom():
    for label in ("19,000원 초과 ~ 23,000원 미만", "19,000원 이상 23,000원 미만", "19,000원(하단) 초과 ~ 23,000원(상단) 미만",
                  "18,000원 이상 ~ 19,000원 미만", "23,000원 미만"):                     # last: the band top, not the bottom
        assert parse_detail(_demand_page((label, "12.50%")))["below_band_pct"] is None, label


def test_below_band_pct_picks_the_bottom_row_among_several():
    page = _demand_page(("19,000원 초과 ~ 23,000원 미만", "30.00%"), ("19,000원 미만", "56.17%"))
    assert parse_detail(page)["below_band_pct"] == 56.17


def test_below_band_pct_plain_row_needs_a_band_bottom():
    assert parse_detail(_demand_page(("19,000원 미만", "56.17%"), band=""))["below_band_pct"] is None   # no band: only the old rule


def test_float_pct_from_the_post_offering_total_row():
    assert parse_detail(_demand_page(float_row="공모후 합계"))["float_pct"] == 36.81
    assert parse_detail(_demand_page(float_row="합계"))["float_pct"] == 36.81
    assert parse_detail(_demand_page(float_row="최대주주등 소계"))["float_pct"] is None
