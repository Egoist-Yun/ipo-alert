import re

from bs4 import BeautifulSoup


class ParseError(Exception):
    pass


_NUM = re.compile(r"-?\d[\d,]*\.?\d*")
_NO = re.compile(r"[?&]no=(\d+)")


def _text(td) -> str:
    return td.get_text(" ", strip=True).replace("\xa0", " ").strip()


def _num(text: str) -> float | None:
    m = _NUM.search(text or "")
    if not m or text.strip() in ("-", ""):
        return None
    return float(m.group().replace(",", ""))


def _int(text: str) -> int | None:
    v = _num(text)
    return None if v is None else int(v)


def _no(tr) -> int | None:
    for a in tr.find_all("a", href=True):
        m = _NO.search(a["href"])
        if m:
            return int(m.group(1))
    return None


def _rows(html: str, date_col: int, date_re: str) -> list[list]:
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for tr in soup.find_all("tr"):
        if tr.find("table"):
            continue
        tds = tr.find_all("td")
        if len(tds) <= date_col or _no(tr) is None:
            continue
        if not re.search(date_re, _text(tds[date_col])):
            continue
        out.append((tr, tds))
    if not out:
        raise ParseError("no rows found")
    return out


def _date(text: str) -> str | None:
    m = re.search(r"(\d{4})[./](\d{2})[./](\d{2})", text or "")
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None


def _range(text: str) -> tuple[str | None, str | None]:
    m = re.search(r"(\d{4})\.(\d{2})\.(\d{2})\s*~\s*(\d{2})\.(\d{2})", text or "")
    if not m:
        return None, None
    y, sm, sd, em, ed = (int(g) for g in m.groups())
    ey = y + 1 if em < sm else y
    return f"{y:04d}-{sm:02d}-{sd:02d}", f"{ey:04d}-{em:02d}-{ed:02d}"


def parse_schedule(html: str) -> list[dict]:
    result = []
    for tr, tds in _rows(html, 1, r"\d{4}\.\d{2}\.\d{2}\s*~"):
        start, end = _range(_text(tds[1]))
        band = re.findall(r"\d[\d,]*", _text(tds[3]))
        result.append({
            "no": _no(tr),
            "name": _text(tds[0]),
            "sub_start": start,
            "sub_end": end,
            "final_price": _int(_text(tds[2])),
            "band_low": int(band[0].replace(",", "")) if len(band) >= 1 else None,
            "band_high": int(band[1].replace(",", "")) if len(band) >= 2 else None,
            "underwriters": [u.strip() for u in _text(tds[5]).split(",") if u.strip()],
        })
    return result


def parse_demand(html: str) -> list[dict]:
    result = []
    for tr, tds in _rows(html, 1, r"\d{4}\.\d{2}\.\d{2}"):
        lock = _text(tds[6]) if len(tds) > 6 else ""
        result.append({
            "no": _no(tr),
            "name": _text(tds[0]),
            "final_price": _int(_text(tds[3])),
            "offer_amount_mil": _int(_text(tds[4])),
            "inst_competition": _num(_text(tds[5])),
            "lockup_pct": _num(lock) if "%" in lock else None,
        })
    return result


def parse_listing(html: str) -> list[dict]:
    result = []
    for tr, tds in _rows(html, 1, r"\d{4}/\d{2}/\d{2}"):
        result.append({
            "no": _no(tr),
            "name": _text(tds[0]),
            "listing_date": _date(_text(tds[1])),
            "final_price": _int(_text(tds[4])),
            "open_price": _int(_text(tds[6])),
            "first_close": _int(_text(tds[8])),
        })
    return result
