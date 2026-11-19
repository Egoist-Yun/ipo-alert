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


def _rows(html: str, date_col: int, date_re: str, min_cols: int) -> list[list]:
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for tr in soup.find_all("tr"):
        if tr.find("table"):
            continue
        tds = tr.find_all("td")
        if len(tds) < min_cols or _no(tr) is None:
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
    for tr, tds in _rows(html, 1, r"\d{4}\.\d{2}\.\d{2}\s*~", 6):
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
    for tr, tds in _rows(html, 1, r"\d{4}\.\d{2}\.\d{2}", 6):
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
    for tr, tds in _rows(html, 1, r"\d{4}/\d{2}/\d{2}", 9):
        result.append({
            "no": _no(tr),
            "name": _text(tds[0]),
            "listing_date": _date(_text(tds[1])),
            "final_price": _int(_text(tds[4])),
            "open_price": _int(_text(tds[6])),
            "first_close": _int(_text(tds[8])),
        })
    return result


def _label_value(soup, label: str) -> str | None:
    for cell in soup.find_all(["td", "th"]):
        if cell.find("table"):
            continue
        if _text(cell).replace(" ", "") == label:
            sib = cell.find_next_sibling(["td", "th"])
            if sib is not None:
                return _text(sib)
    return None


def _full_range(text: str | None) -> tuple[str | None, str | None]:
    found = re.findall(r"\d{4}\.\d{2}\.\d{2}", text or "")
    if len(found) >= 2:
        return _date(found[0]), _date(found[1])
    return None, None


def _last_pct(cells: list[str]) -> float | None:
    for c in reversed(cells):
        if "%" in c and _num(c) is not None:
            return _num(c)
    return None


def _old_share(offering: str | None) -> float | None:
    if not offering:
        return None
    old = re.search(r"구주매출[^()]*\((\d+(?:\.\d+)?)%\)", offering)
    if old:
        return float(old.group(1))
    new = re.search(r"신주모집[^()]*\((\d+(?:\.\d+)?)%\)", offering)
    return round(100.0 - float(new.group(1)), 2) if new else None


def _inst_count(soup) -> int | None:
    text = soup.get_text(" ", strip=True)
    m = re.search(r"참여건수\s*\(단위:건\)\s*신청주식수\s*\(단위:주\)\s*단순경쟁\s*([\d,]+)", text)
    return int(m.group(1).replace(",", "")) if m else None


def _share_range(text: str | None) -> tuple[int | None, int | None]:
    """'542,500~651,000 주 (25.0~30.0%)' -> (542500, 651000); a single value -> (value, None); nothing -> (None, None)."""
    m = re.search(r"([\d,]+)\s*~\s*([\d,]+)\s*주", text or "")
    if m:
        return int(m.group(1).replace(",", "")), int(m.group(2).replace(",", ""))
    return _int(text or ""), None


def _retail_deposit_pct(soup) -> float | None:
    """The deposit rate of the retail side (the page also shows the institutional 100%): it follows the 일반청약자 share."""
    text = soup.get_text(" ", strip=True)
    m = re.search(r"일반청약자\s*[\d,]+(?:\s*~\s*[\d,]+)?\s*주\s*\(\s*[\d.]+%?(?:\s*~\s*[\d.]+%?)?\s*\)\s*청약증거금율\s*:\s*(\d+(?:\.\d+)?)\s*%", text)  # shares/percent are ranges before the offer is fixed
    return float(m.group(1)) if m else None


def _brokers(soup) -> list[dict]:
    """The underwriter table (인수회사 | 주식수 | 청약한도 | 기타). Not every page has it: then an empty list."""
    for table in soup.find_all("table"):
        if table.find("table"):
            continue
        rows = [[_text(c) for c in tr.find_all(["td", "th"])] for tr in table.find_all("tr")]
        if not rows or len(rows[0]) < 3 or rows[0][0] != "인수회사":
            continue
        out = []
        for cells in rows[1:]:
            if len(cells) < 3 or not cells[0]:
                continue
            numbers = [int(n.replace(",", "")) for n in re.findall(r"\d[\d,]*", cells[2])]
            out.append({"name": cells[0], "shares": _int(cells[1]), "limit_text": cells[2],
                        "limit_max": max(numbers) if numbers else None})
        return out
    return []


def parse_detail(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    band = re.findall(r"\d[\d,]*", _label_value(soup, "희망공모가액") or "")
    sub_start, sub_end = _full_range(_label_value(soup, "공모청약일"))
    demand_start, demand_end = _full_range(_label_value(soup, "수요예측일"))
    retail_shares, retail_shares_high = _share_range(_label_value(soup, "일반청약자"))
    lock = _label_value(soup, "의무보유확약") or ""

    below_band = None
    float_pct = None
    for table in soup.find_all("table"):
        if table.find("table"):
            continue
        for tr in table.find_all("tr"):
            cells = [_text(c) for c in tr.find_all(["td", "th"])]
            if not cells:
                continue
            if below_band is None and re.search(r"\(하단\)\s*미만", cells[0]):
                below_band = _last_pct(cells)
            if float_pct is None and cells[0] == "합계" and "유통가능" in _text(table):
                float_pct = _last_pct(cells)

    return {
        "market": _label_value(soup, "시장구분"),
        "industry": _label_value(soup, "업종"),
        "band_low": int(band[0].replace(",", "")) if len(band) >= 1 else None,
        "band_high": int(band[1].replace(",", "")) if len(band) >= 2 else None,
        "final_price": _int(_label_value(soup, "확정공모가") or ""),
        "offer_amount_mil": _int(_label_value(soup, "공모금액") or ""),
        "sub_start": sub_start,
        "sub_end": sub_end,
        "listing_date": _date(_label_value(soup, "신규상장일") or ""),
        "inst_competition": _num(_label_value(soup, "기관경쟁률") or ""),
        "lockup_pct": _num(lock) if "%" in lock else None,
        "below_band_pct": below_band,
        "float_pct": float_pct,
        "revenue_mil": _int(_label_value(soup, "매출액") or ""),
        "net_income_mil": _int(_label_value(soup, "순이익") or ""),
        "capital_mil": _int(_label_value(soup, "자본금") or ""),
        "par_value": _int(_label_value(soup, "액면가") or ""),
        "old_share_pct": _old_share(_label_value(soup, "상장공모")),
        "inst_count": _inst_count(soup),
        "retail_competition": _num(_label_value(soup, "청약경쟁률") or ""),
        "total_shares": _int(_label_value(soup, "총공모주식수") or ""),
        "retail_shares": retail_shares,
        "retail_shares_high": retail_shares_high,
        "retail_deposit_pct": _retail_deposit_pct(soup),
        "refund_date": _date(_label_value(soup, "환불일") or ""),
        "demand_start": demand_start,
        "demand_end": demand_end,
        "brokers": _brokers(soup),
    }
