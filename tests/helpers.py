from pathlib import Path

FIX = Path(__file__).parent / "fixtures"


def load(name: str) -> str:
    return (FIX / f"{name}.html").read_bytes().decode("euc-kr", errors="replace")


# A detail page that is recognisably one (it has an anchor label) but carries nothing else: for fakes and "missing parts are None" checks.
BARE_DETAIL = "<html><body><table><tr><td>공모청약일</td><td>-</td></tr></table>종목명 X</body></html>"
