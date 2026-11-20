import json
from dataclasses import asdict, fields
from pathlib import Path
from statistics import median

from ipo import config
from ipo.collect import apply_detail, check_detail_failures, detail_failure, detail_url, market_mood
from ipo.fetch import FetchError, get_html
from ipo.models import Ipo, first_day_return
from ipo.parse import ParseError, parse_detail, parse_listing
from ipo.signals import score


# Listed stocks without a first-day close are normal in small numbers (listing today, price not out yet: ~25% of a real page).
# When half or more of the non-spac rows lack it, the table's columns moved and the history would silently stop growing.
MAX_NO_CLOSE_RATIO = 0.5
MAX_UPDATE_PAGES = 5  # a run reads listing pages until it meets a stock it already knows, but never more than this many


def _listed_rows(pages: range, fetch) -> list[dict]:
    rows = []
    for page in pages:
        page_rows = [r for r in parse_listing(fetch(config.BASE_URL + f"index.htm?o=nw&page={page}")) if "스팩" not in r["name"]]
        missing = sum(1 for r in page_rows if r["first_close"] is None)
        if page_rows and missing / len(page_rows) >= MAX_NO_CLOSE_RATIO:
            raise ParseError(f"{missing} of {len(page_rows)} listed rows have no first-day close (layout changed?)")
        rows += page_rows
    return [r for r in rows if r["first_close"] is not None]


def _make(row: dict, fetch) -> Ipo:
    ipo = Ipo(no=row["no"], name=row["name"], url=detail_url(row["no"]),
              listing_date=row["listing_date"], final_price=row["final_price"],
              open_price=row["open_price"], first_close=row["first_close"])
    apply_detail(ipo, parse_detail(fetch(ipo.url)))
    return ipo


def _make_all(rows: list[dict], fetch, failures: list | None) -> list[Ipo]:
    """Each stock on its own: one failing detail page skips that stock (it is retried next run); too many failures raise."""
    made, failed = [], []
    for row in rows:
        try:
            made.append(_make(row, fetch))
        except (ParseError, FetchError) as e:
            failed.append(detail_failure(row["no"], row["name"], e))
    check_detail_failures(failed, len(rows))
    if failures is not None:
        failures.extend(failed)
    return made


def build_history(pages: int, fetch=get_html, failures: list | None = None) -> list[Ipo]:
    items = _make_all(_listed_rows(range(1, pages + 1), fetch), fetch, failures)
    return sorted(items, key=lambda i: (i.listing_date or "", i.no))


def update_history(existing: list[Ipo], fetch=get_html, failures: list | None = None) -> list[Ipo]:
    known = {i.no for i in existing}
    rows = []
    for page in range(1, MAX_UPDATE_PAGES + 1):
        page_rows = _listed_rows(range(page, page + 1), fetch)
        rows += [r for r in page_rows if r["no"] not in known and r["no"] not in {x["no"] for x in rows}]
        if any(r["no"] in known for r in page_rows):
            break  # reached stocks we already have: nothing older is new
    new = _make_all(rows, fetch, failures)
    return sorted(existing + new, key=lambda i: (i.listing_date or "", i.no))


def save_history(path, items: list[Ipo]) -> None:
    Path(path).write_text(json.dumps([asdict(i) for i in items], ensure_ascii=False), encoding="utf-8")


def load_history(path) -> list[Ipo]:
    names = {f.name for f in fields(Ipo)}
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [Ipo(**{k: v for k, v in d.items() if k in names}) for d in data]


def signal_backtest(history: list[Ipo]) -> str:
    groups: dict[int, list[float]] = {}
    for ipo in history:
        ret = first_day_return(ipo)
        if ipo.is_spac or ret is None or not ipo.listing_date:
            continue
        scored = score(ipo, market_mood(history, ipo.sub_start or ipo.listing_date))
        groups.setdefault(scored.flag_count, []).append(ret)
    lines = ["| 신호 개수 | 종목 수 | 공모가 아래로 끝난 비율 | 첫날 등락률 가운데 값 |",
             "|---|---|---|---|"]
    for count in sorted(groups):
        rets = groups[count]
        down = sum(1 for r in rets if r < 0) / len(rets)
        lines.append(f"| {count} | {len(rets)} | {down * 100:.0f}% | {median(rets) * 100:+.1f}% |")
    return "\n".join(lines) + "\n"
