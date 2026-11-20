import re
from datetime import datetime

from ipo import config
from ipo.fetch import FetchError, get_html
from ipo.models import Ipo, first_day_return
from ipo.parse import ParseError, parse_demand, parse_detail, parse_listing, parse_schedule

_BIO = re.compile(r"의약|의학|생물|바이오")


def _fill(ipo: Ipo, **fields) -> None:
    for key, value in fields.items():
        if value is None or value == []:
            continue
        if getattr(ipo, key) in (None, []):
            setattr(ipo, key, value)


# A single stock's detail page can fail on its own (a withdrawn listing, a maintenance page), so that stock is skipped and reported.
# But when more than ~30% of the attempted pages fail the site layout changed, and the whole run must fail loudly instead.
MAX_DETAIL_FAIL_RATIO = 0.3


def detail_failure(no: int, name: str, error: Exception) -> dict:
    return {"no": no, "name": name, "error": f"{type(error).__name__}: {error}"}


def check_detail_failures(failures: list[dict], attempted: int) -> None:
    if attempted and len(failures) / attempted > MAX_DETAIL_FAIL_RATIO:
        names = ", ".join(f["name"] for f in failures)
        raise ParseError(f"{len(failures)} of {attempted} detail pages failed (layout changed?): {names}")


def detail_url(no: int) -> str:
    return f"{config.BASE_URL}?o=v&no={no}"


def apply_detail(ipo: Ipo, detail: dict) -> None:
    ipo.market = detail["market"]
    ipo.industry = detail["industry"]
    ipo.below_band_pct = detail["below_band_pct"]
    ipo.float_pct = detail["float_pct"]
    for key in ("revenue_mil", "net_income_mil", "capital_mil", "par_value", "old_share_pct", "inst_count",
                "retail_competition"):
        setattr(ipo, key, detail[key])
    _fill(ipo, **{k: detail[k] for k in (
        "band_low", "band_high", "final_price", "offer_amount_mil", "sub_start", "sub_end",
        "listing_date", "inst_competition", "lockup_pct")})
    # subscription facts: overwritten each time, but a page that lacks one never erases what was collected before
    for key in ("total_shares", "retail_shares", "retail_deposit_pct", "refund_date", "demand_start", "demand_end", "brokers"):
        value = detail.get(key)
        if value not in (None, []):
            setattr(ipo, key, value)
    # the upper end only exists while the retail share is a range: once the offer is fixed it must go back to None
    if detail.get("retail_shares") is not None:
        ipo.retail_shares_high = detail.get("retail_shares_high")
    ipo.is_bio = bool(ipo.industry and _BIO.search(ipo.industry))


def collect_current(fetch=get_html, cache: dict | None = None, today: str | None = None,
                    failures: list | None = None) -> list[Ipo]:
    """`failures` (if given) receives {no, name, error} for each stock whose detail page was skipped."""
    today = today or datetime.now(config.KST).date().isoformat()
    cache = {} if cache is None else cache

    tables = (
        parse_schedule(fetch(config.BASE_URL + "index.htm?o=k")),
        parse_demand(fetch(config.BASE_URL + "index.htm?o=r1")),
        parse_listing(fetch(config.BASE_URL + "index.htm?o=nw")),
    )
    rated = [r for r in tables[1] if "스팩" not in r["name"]]
    if rated and all(r["inst_competition"] is None for r in rated):
        raise ParseError("demand table has no competition values (layout changed?)")
    by_no: dict[int, Ipo] = {}
    for rows in tables:
        for row in rows:
            row = dict(row)
            no, name = row.pop("no"), row.pop("name")
            ipo = by_no.setdefault(no, Ipo(no=no, name=name, url=detail_url(no)))
            _fill(ipo, **row)

    failed: list[dict] = []
    attempted = 0
    for ipo in by_no.values():
        ipo.is_spac = "스팩" in ipo.name
        if ipo.is_spac:
            continue
        wanted = ipo.inst_competition is not None or (ipo.sub_start is not None and ipo.sub_start >= today)
        if not wanted:
            continue
        if ipo.no in cache:
            detail = cache[ipo.no]
        else:
            attempted += 1
            try:
                detail = parse_detail(fetch(detail_url(ipo.no)))
            except (ParseError, FetchError) as e:
                failed.append(detail_failure(ipo.no, ipo.name, e))
                continue  # the table values stay; nothing is cached for this stock, it is tried again next run
            if ipo.inst_competition is not None:
                cache[ipo.no] = detail
        apply_detail(ipo, detail)
    check_detail_failures(failed, attempted)
    if failures is not None:
        failures.extend(failed)
    return list(by_no.values())


def _recent_window(history: list[Ipo], before: str) -> list[Ipo] | None:
    done = [i for i in history
            if not i.is_spac and i.listing_date and i.listing_date < before
            and first_day_return(i) is not None]
    done.sort(key=lambda i: (i.listing_date, i.no), reverse=True)
    window = done[: config.MOOD_WINDOW]
    return window if len(window) >= config.MOOD_WINDOW else None


def market_mood(history: list[Ipo], before: str) -> float | None:
    window = _recent_window(history, before)
    if window is None:
        return None
    return sum(1 for i in window if first_day_return(i) < 0) / len(window)


def market_heat(history: list[Ipo], before: str) -> float | None:
    """Median first-day return of the most recent listings (how hot the market is, not just how many fell)."""
    window = _recent_window(history, before)
    if window is None:
        return None
    return float(sorted(first_day_return(i) for i in window)[len(window) // 2])
