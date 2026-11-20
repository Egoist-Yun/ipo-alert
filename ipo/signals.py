from dataclasses import replace

from ipo import config
from ipo.models import Ipo


def _num(x) -> str:
    return f"{x:g}"


def _at_least(threshold: float, value):
    """severity of an 'at least' rule: the fraction by which the value is beyond the threshold (0 inside the safe side)."""
    return None if value is None else round(max(0.0, (value - threshold) / threshold), 4)


def _below(threshold: float, value):
    """severity of a 'below' rule: the fraction by which the value falls short of the threshold (0 on the safe side)."""
    return None if value is None else round(max(0.0, (threshold - value) / threshold), 4)


def _signal(key, label, value, flag, rule, severity):
    return {"key": key, "label": label, "value": value, "flag": None if value is None else flag,
            "rule": rule, "severity": severity}


def score(ipo: Ipo, mood: float | None) -> Ipo:
    if ipo.is_spac:
        return replace(ipo, signals=[], flag_count=0, unknown_count=0)

    at_low = None
    if ipo.final_price is not None and ipo.band_low is not None:
        at_low = ipo.final_price <= ipo.band_low

    def cmp(value, fn):
        return None if value is None else fn(value)

    signals = [
        {"key": "price_position", "label": "공모가 위치", "value": ipo.final_price, "flag": at_low,
         "rule": "하단 이하", "severity": _below(ipo.band_low, ipo.final_price) if at_low is not None else None},
        _signal("inst_competition", "기관 경쟁률", ipo.inst_competition,
                cmp(ipo.inst_competition, lambda v: v < config.MIN_INST_COMPETITION),
                f"{_num(config.MIN_INST_COMPETITION)}대 1 미만", _below(config.MIN_INST_COMPETITION, ipo.inst_competition)),
        _signal("lockup", "의무보유확약", ipo.lockup_pct,
                cmp(ipo.lockup_pct, lambda v: v < config.MIN_LOCKUP_PCT),
                f"{_num(config.MIN_LOCKUP_PCT)}% 미만", _below(config.MIN_LOCKUP_PCT, ipo.lockup_pct)),
        _signal("below_band", "하단 미만 신청", ipo.below_band_pct,
                cmp(ipo.below_band_pct, lambda v: v >= config.MAX_BELOW_BAND_PCT),
                f"{_num(config.MAX_BELOW_BAND_PCT)}% 이상", _at_least(config.MAX_BELOW_BAND_PCT, ipo.below_band_pct)),
        _signal("float", "유통가능물량", ipo.float_pct,
                cmp(ipo.float_pct, lambda v: v >= config.MAX_FLOAT_PCT),
                f"{_num(config.MAX_FLOAT_PCT)}% 이상", _at_least(config.MAX_FLOAT_PCT, ipo.float_pct)),
        _signal("mood", "최근 시장 분위기", mood,
                cmp(mood, lambda v: v >= config.MOOD_BAD_RATIO),
                f"{round(config.MOOD_BAD_RATIO * config.MOOD_WINDOW)}/{config.MOOD_WINDOW} 이상",
                _at_least(config.MOOD_BAD_RATIO, mood)),
    ]
    return replace(
        ipo,
        signals=signals,
        flag_count=sum(1 for s in signals if s["flag"] is True),
        unknown_count=sum(1 for s in signals if s["flag"] is None),
    )
