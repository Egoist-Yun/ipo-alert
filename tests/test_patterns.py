from dataclasses import replace

import pytest

from ipo.models import Ipo
from ipo.patterns import PATTERNS, match_patterns, pattern_stats

NEXI = Ipo(no=2336, name="넥스아이", url="", band_low=10500, band_high=13000, final_price=8000,
           inst_competition=66.58, lockup_pct=0.06)


def past(no, *, lock, comp, low=100, final=110, close=None, open_=None, date="2024-01-10", spac=False):
    return Ipo(no=no, name=f"s{no}", url="", band_low=low, band_high=low + 20, final_price=final,
               inst_competition=comp, lockup_pct=lock, first_close=close, open_price=open_,
               listing_date=date, is_spac=spac)


def stats_with_room():
    return {p.key: {"n": 30, "close_down": 0.75, "open_down": 0.5} for p in PATTERNS}


def keys(matches):
    return {m["key"] for m in matches}


def test_nexi_matches_all_pre_subscription_risk_patterns():
    assert keys(match_patterns(NEXI, stats_with_room())) == {"lock_comp", "lock_low", "comp_low"}


def test_post_subscription_pattern_needs_retail_competition():
    after = replace(NEXI, retail_competition=13.26)
    assert "retail_lock" in keys(match_patterns(after, stats_with_room()))


def test_missing_values_never_match():
    assert keys(match_patterns(replace(NEXI, lockup_pct=None), stats_with_room())) == {"comp_low"}


def test_safe_pattern_for_strong_demand():
    strong = replace(NEXI, inst_competition=1500, lockup_pct=5.0, final_price=13000)
    found = match_patterns(strong, stats_with_room())
    assert keys(found) == {"strong"} and found[0]["kind"] == "safe"


def test_patterns_with_too_few_past_cases_are_hidden():
    thin = stats_with_room()
    thin["lock_comp"]["n"] = 9
    assert "lock_comp" not in keys(match_patterns(NEXI, thin, min_n=10))


def test_spac_is_never_matched():
    assert match_patterns(replace(NEXI, is_spac=True), stats_with_room()) == []


def test_pattern_stats_counts_only_current_regime_listings_with_results():
    hist = [
        past(1, lock=0.5, comp=50, close=90, open_=95),                       # lock_comp, closes down, opens down
        past(2, lock=0.5, comp=50, close=130, open_=140),                     # lock_comp, up
        past(3, lock=0.5, comp=50, close=80, open_=120),                      # lock_comp, close down, open up
        past(4, lock=0.5, comp=50, close=80, date="2022-01-01"),              # old regime: excluded
        past(5, lock=0.5, comp=50, close=None),                               # not listed yet: excluded
        past(6, lock=0.5, comp=50, close=50, spac=True),                      # spac: excluded
    ]
    s = pattern_stats(hist, since="2023-06-26")["lock_comp"]
    assert s["n"] == 3
    assert s["close_down"] == pytest.approx(2 / 3) and s["open_down"] == pytest.approx(1 / 3)
