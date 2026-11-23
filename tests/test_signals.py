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


def _by_key(ipo, mood=None):
    return {x["key"]: x for x in score(ipo, mood).signals}


def test_every_signal_carries_its_rule_text_from_config():
    sig = _by_key(NEXI, 0.6)
    assert sig["below_band"]["rule"] == "20% 이상"
    assert sig["lockup"]["rule"] == "5% 미만"
    assert sig["inst_competition"]["rule"] == "300대 1 미만"
    assert sig["price_position"]["rule"] == "하단 이하"
    assert sig["float"]["rule"] == "35% 이상"
    assert sig["mood"]["rule"] == "5/10 이상"


def test_severity_for_at_least_rules_is_the_fraction_beyond_the_threshold():
    sig = _by_key(replace(NEXI, below_band_pct=40.0, float_pct=70.0), 0.75)
    assert sig["below_band"]["severity"] == 1.0           # (40 - 20) / 20
    assert sig["float"]["severity"] == 1.0                # (70 - 35) / 35
    assert sig["mood"]["severity"] == 0.5                 # (0.75 - 0.5) / 0.5


def test_severity_for_below_rules_is_the_fraction_short_of_the_threshold():
    sig = _by_key(replace(NEXI, inst_competition=150.0, lockup_pct=2.5), None)
    assert sig["inst_competition"]["severity"] == 0.5     # (300 - 150) / 300
    assert sig["lockup"]["severity"] == 0.5               # (5 - 2.5) / 5


def test_severity_is_zero_at_the_boundary_one_for_a_zero_value_and_never_negative():
    sig = _by_key(replace(NEXI, inst_competition=300, lockup_pct=5.0, below_band_pct=20.0, float_pct=35.0), 0.5)
    assert all(sig[k]["severity"] == 0.0 for k in ("inst_competition", "lockup", "below_band", "float", "mood"))
    assert _by_key(replace(NEXI, lockup_pct=0.0))["lockup"]["severity"] == 1.0      # a zero lock-up is the largest shortfall: 1, not infinite
    safe = _by_key(replace(NEXI, inst_competition=1200, lockup_pct=20.0, below_band_pct=0.0, float_pct=10.0), 0.1)
    assert all(safe[k]["severity"] == 0.0 for k in ("inst_competition", "lockup", "below_band", "float", "mood"))


def test_ucast_severity_order_puts_the_below_band_order_flow_first():
    ucast = replace(NEXI, band_low=19000, final_price=19000, inst_competition=173.4, lockup_pct=0.57, below_band_pct=56.17, float_pct=36.81)
    sig = _by_key(ucast, 0.6)
    order = sorted((k for k in sig), key=lambda k: -(sig[k]["severity"] or 0))
    assert order == ["below_band", "lockup", "inst_competition", "mood", "float", "price_position"]   # fixed exactly at the bottom: severity 0, last
    assert round(sig["below_band"]["severity"], 2) == 1.81 and round(sig["lockup"]["severity"], 2) == 0.89


def test_severity_of_price_position_and_missing_values():
    assert _by_key(replace(NEXI, final_price=8000, band_low=10500))["price_position"]["severity"] == 0.2381     # (10500 - 8000) / 10500
    assert _by_key(replace(NEXI, final_price=7000, band_low=9600))["price_position"]["severity"] == 0.2708
    at_low = _by_key(replace(NEXI, final_price=19000, band_low=19000))["price_position"]
    assert at_low["severity"] == 0.0 and at_low["flag"] is True       # exactly at the bottom: still a risk signal, no distance below it
    above = _by_key(replace(NEXI, final_price=13000, band_low=10500))["price_position"]
    assert above["severity"] == 0.0 and above["flag"] is False       # above the bottom
    assert _by_key(replace(NEXI, final_price=None))["price_position"]["severity"] is None
    assert _by_key(replace(NEXI, band_low=None))["price_position"]["severity"] is None
    sig = _by_key(OPTONICS, None)
    assert sig["below_band"]["severity"] is None and sig["float"]["severity"] is None and sig["mood"]["severity"] is None
    assert sig["below_band"]["rule"] == "20% 이상"            # the rule text is shown even when the value is unknown


def test_every_signal_key_has_a_glossary_entry_in_the_web_app():
    """The detail screen shows a help bubble per signal key (web/calendar.js GLOSSARY); a renamed or new key must get one."""
    import re
    from pathlib import Path
    js = (Path(__file__).resolve().parent.parent / "web" / "calendar.js").read_text(encoding="utf-8")
    block = re.search(r"export const GLOSSARY = \{(.*?)\n\};", js, re.S)
    assert block, "GLOSSARY block not found in web/calendar.js"
    glossary = set(re.findall(r"^\s*(\w+):", block.group(1), re.M))
    assert glossary, "no GLOSSARY keys parsed"
    keys = set(_by_key(NEXI, 0.6))
    assert keys == {"price_position", "inst_competition", "lockup", "below_band", "float", "mood"}
    assert keys <= glossary
