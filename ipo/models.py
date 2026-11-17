from dataclasses import dataclass, field


@dataclass
class Ipo:
    no: int
    name: str
    url: str
    market: str | None = None
    industry: str | None = None
    is_spac: bool = False
    is_bio: bool = False
    sub_start: str | None = None
    sub_end: str | None = None
    listing_date: str | None = None
    band_low: int | None = None
    band_high: int | None = None
    final_price: int | None = None
    underwriters: list[str] = field(default_factory=list)
    offer_amount_mil: int | None = None
    inst_competition: float | None = None
    lockup_pct: float | None = None
    below_band_pct: float | None = None
    float_pct: float | None = None
    revenue_mil: int | None = None
    net_income_mil: int | None = None
    capital_mil: int | None = None
    par_value: int | None = None
    old_share_pct: float | None = None
    inst_count: int | None = None
    open_price: int | None = None
    first_close: int | None = None
    signals: list[dict] = field(default_factory=list)
    flag_count: int = 0
    unknown_count: int = 0
    prediction: dict | None = None


def first_day_return(ipo: Ipo) -> float | None:
    if ipo.first_close is None or not ipo.final_price:
        return None
    return ipo.first_close / ipo.final_price - 1
