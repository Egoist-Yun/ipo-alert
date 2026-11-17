from dataclasses import replace

from ipo import config
from ipo.models import Ipo


def _signal(key, label, value, flag):
    return {"key": key, "label": label, "value": value, "flag": None if value is None else flag}


def score(ipo: Ipo, mood: float | None) -> Ipo:
    if ipo.is_spac:
        return replace(ipo, signals=[], flag_count=0, unknown_count=0)

    at_low = None
    if ipo.final_price is not None and ipo.band_low is not None:
        at_low = ipo.final_price <= ipo.band_low

    def cmp(value, fn):
        return None if value is None else fn(value)

    signals = [
        {"key": "price_position", "label": "공모가 위치", "value": ipo.final_price, "flag": at_low},
        _signal("inst_competition", "기관 경쟁률", ipo.inst_competition,
                cmp(ipo.inst_competition, lambda v: v < config.MIN_INST_COMPETITION)),
        _signal("lockup", "의무보유확약", ipo.lockup_pct,
                cmp(ipo.lockup_pct, lambda v: v < config.MIN_LOCKUP_PCT)),
        _signal("below_band", "하단 미만 신청", ipo.below_band_pct,
                cmp(ipo.below_band_pct, lambda v: v >= config.MAX_BELOW_BAND_PCT)),
        _signal("float", "유통가능물량", ipo.float_pct,
                cmp(ipo.float_pct, lambda v: v >= config.MAX_FLOAT_PCT)),
        _signal("mood", "최근 시장 분위기", mood,
                cmp(mood, lambda v: v >= config.MOOD_BAD_RATIO)),
    ]
    return replace(
        ipo,
        signals=signals,
        flag_count=sum(1 for s in signals if s["flag"] is True),
        unknown_count=sum(1 for s in signals if s["flag"] is None),
    )
