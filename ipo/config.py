PRICE_AT_OR_BELOW_LOW = True
MIN_INST_COMPETITION = 300
MIN_LOCKUP_PCT = 5.0
MAX_BELOW_BAND_PCT = 20.0
MAX_FLOAT_PCT = 35.0
MOOD_WINDOW = 10
MOOD_BAD_RATIO = 0.5

DISCLAIMER = "투자 권유가 아닌 공개 정보 정리입니다. 청약 판단은 본인이 하세요."

BASE_URL = "https://www.38.co.kr/html/fund/"

from datetime import timedelta, timezone

KST = timezone(timedelta(hours=9))  # fixed offset: Windows lacks a tz database by default
