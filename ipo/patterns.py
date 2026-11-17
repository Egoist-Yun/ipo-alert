"""Plain-language decline patterns found in the 2015+ history (see data/backtest.md).

Thresholds are fixed round numbers; how often each pattern ended below the offer price is
recomputed on every run from listings since the 2023-06-26 price-band change."""
from dataclasses import dataclass
from typing import Callable

from ipo.models import Ipo, first_day_return

REGIME_START = "2023-06-26"  # first-day price band widened to 60-400% of the offer price
MIN_CASES = 10


def _lock_lt1(i: Ipo):
    return None if i.lockup_pct is None else i.lockup_pct < 1


def _comp_lt300(i: Ipo):
    return None if i.inst_competition is None else i.inst_competition < 300


def _at_or_below_low(i: Ipo):
    return None if i.final_price is None or i.band_low is None else i.final_price <= i.band_low


def _retail_lt100(i: Ipo):
    return None if i.retail_competition is None else i.retail_competition < 100


def _strong(i: Ipo):
    if i.inst_competition is None or i.lockup_pct is None:
        return None
    return i.inst_competition > 1000 and i.lockup_pct >= 3


def _all(*tests):
    def check(i: Ipo):
        values = [t(i) for t in tests]
        return None if any(v is None for v in values) else all(values)
    return check


@dataclass(frozen=True)
class Pattern:
    key: str
    label: str
    phase: str   # "pre": known before subscribing, "post": known after the subscription closes
    kind: str    # "risk" or "safe"
    test: Callable[[Ipo], bool | None]


PATTERNS = [
    Pattern("lock_comp", "의무보유확약 1% 미만 + 기관 경쟁률 300대 1 미만", "pre", "risk", _all(_lock_lt1, _comp_lt300)),
    Pattern("lock_low", "의무보유확약 1% 미만 + 공모가 희망 범위 하단 이하", "pre", "risk", _all(_lock_lt1, _at_or_below_low)),
    Pattern("comp_low", "기관 경쟁률 300대 1 미만 + 공모가 희망 범위 하단 이하", "pre", "risk", _all(_comp_lt300, _at_or_below_low)),
    Pattern("retail_lock", "일반청약 경쟁률 100대 1 미만 + 의무보유확약 1% 미만", "post", "risk", _all(_retail_lt100, _lock_lt1)),
    Pattern("strong", "기관 경쟁률 1000대 1 초과 + 의무보유확약 3% 이상", "pre", "safe", _strong),
]


def _open_return(i: Ipo):
    return i.open_price / i.final_price - 1 if i.open_price and i.final_price else None


def pattern_stats(history: list[Ipo], since: str = REGIME_START) -> dict[str, dict]:
    done = [i for i in history if not i.is_spac and i.listing_date and i.listing_date >= since
            and first_day_return(i) is not None]
    out = {}
    for p in PATTERNS:
        hit = [i for i in done if p.test(i) is True]
        opens = [r for r in (_open_return(i) for i in hit) if r is not None]
        out[p.key] = {
            "n": len(hit),
            "close_down": (sum(1 for i in hit if first_day_return(i) < 0) / len(hit)) if hit else None,
            "open_down": (sum(1 for r in opens if r < 0) / len(opens)) if opens else None,
        }
    return out


def match_patterns(ipo: Ipo, stats: dict[str, dict], min_n: int = MIN_CASES) -> list[dict]:
    if ipo.is_spac:
        return []
    out = []
    for p in PATTERNS:
        s = stats.get(p.key)
        if not s or s["n"] < min_n or p.test(ipo) is not True:
            continue
        out.append({"key": p.key, "label": p.label, "phase": p.phase, "kind": p.kind, **s})
    return out
