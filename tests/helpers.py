from pathlib import Path

FIX = Path(__file__).parent / "fixtures"


def load(name: str) -> str:
    return (FIX / f"{name}.html").read_bytes().decode("euc-kr", errors="replace")
