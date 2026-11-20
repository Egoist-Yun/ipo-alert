import pytest

from ipo.fetch import FetchError, decode_page
from tests.helpers import FIX


def test_real_fixture_bytes_decode_cleanly():
    for path in sorted(FIX.glob("*.html")):
        text = decode_page(path.read_bytes(), "https://x/")
        assert "�" not in text and "공모" in text


def test_cp949_extended_hangul_decodes_where_euc_kr_would_replace():
    raw = "똠방각하".encode("cp949")           # 똠 exists in cp949 only
    assert "똠" in decode_page(raw, "https://x/")


def test_garbled_bytes_raise_fetch_error_with_the_url():
    garbled = ("한글 공모주 페이지 " * 20).encode("utf-8")        # UTF-8 read as cp949: the typical wrong-encoding symptom
    with pytest.raises(FetchError) as e:
        decode_page(garbled, "https://x/page")
    assert "https://x/page" in str(e.value)


def test_a_few_replacement_characters_are_tolerated():
    raw = "공모주".encode("cp949") + bytes([0xFF]) + "정상".encode("cp949")
    assert "공모주" in decode_page(raw, "https://x/")
