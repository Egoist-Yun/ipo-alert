from dataclasses import replace

from ipo.models import Ipo
from ipo.signals import score

NEXI = Ipo(no=2336, name="넥스아이", url="", band_low=10500, band_high=13000, final_price=8000,
           inst_competition=66.58, lockup_pct=0.06, below_band_pct=48.15, float_pct=36.97)
OPTONICS = Ipo(no=1, name="옵토닉스", url="", band_low=10000, band_high=12000, final_price=12000,
               inst_competition=1201.81, lockup_pct=5.62, below_band_pct=None, float_pct=None)


def test_nexi_has_at_least_4_flags():
    assert score(NEXI, mood=None).flag_count >= 4


def test_good_ipo_has_at_most_1_flag():
    assert score(OPTONICS, mood=0.2).flag_count <= 1


def test_missing_values_are_unknown_not_flagged():
    s = score(OPTONICS, mood=None)
    assert s.unknown_count == 3
    assert all(sig["flag"] is None for sig in s.signals if sig["value"] is None)


def test_boundaries():
    s = score(replace(NEXI, inst_competition=300, lockup_pct=5.0, below_band_pct=20.0, float_pct=35.0), None)
    flags = {x["key"]: x["flag"] for x in s.signals}
    assert flags["inst_competition"] is False and flags["lockup"] is False
    assert flags["below_band"] is True and flags["float"] is True


def test_price_position_flag_when_at_band_low():
    s = score(replace(NEXI, band_low=8000), None)
    assert {x["key"]: x["flag"] for x in s.signals}["price_position"] is True


def test_mood_flag_at_half():
    flags = {x["key"]: x["flag"] for x in score(OPTONICS, mood=0.5).signals}
    assert flags["mood"] is True


def test_spac_not_scored():
    s = score(Ipo(no=9, name="신영스팩12호", url="", is_spac=True), None)
    assert s.signals == [] and s.flag_count == 0 and s.unknown_count == 0


def test_score_does_not_mutate_input():
    score(NEXI, None)
    assert NEXI.signals == []
