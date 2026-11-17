import json
from dataclasses import asdict, fields
from pathlib import Path
from statistics import median

from ipo import config
from ipo.collect import apply_detail, detail_url, market_mood
from ipo.fetch import get_html
from ipo.models import Ipo, first_day_return
from ipo.parse import parse_detail, parse_listing
from ipo.signals import score


def _listed_rows(pages: range, fetch) -> list[dict]:
    rows = []
    for page in pages:
        rows += parse_listing(fetch(config.BASE_URL + f"index.htm?o=nw&page={page}"))
    return [r for r in rows if r["first_close"] is not None and "스팩" not in r["name"]]


def _make(row: dict, fetch) -> Ipo:
    ipo = Ipo(no=row["no"], name=row["name"], url=detail_url(row["no"]),
              listing_date=row["listing_date"], final_price=row["final_price"],
              open_price=row["open_price"], first_close=row["first_close"])
    apply_detail(ipo, parse_detail(fetch(ipo.url)))
    return ipo


def build_history(pages: int, fetch=get_html) -> list[Ipo]:
    items = [_make(r, fetch) for r in _listed_rows(range(1, pages + 1), fetch)]
    return sorted(items, key=lambda i: (i.listing_date or "", i.no))


def update_history(existing: list[Ipo], fetch=get_html) -> list[Ipo]:
    known = {i.no for i in existing}
    new = [_make(r, fetch) for r in _listed_rows(range(1, 2), fetch) if r["no"] not in known]
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
