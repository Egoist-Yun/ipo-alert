PRICE_AT_OR_BELOW_LOW = True
MIN_INST_COMPETITION = 300
MIN_LOCKUP_PCT = 5.0
MAX_BELOW_BAND_PCT = 20.0
MAX_FLOAT_PCT = 35.0
MOOD_WINDOW = 10
MOOD_BAD_RATIO = 0.5

APP_NAME = "공모주 달력"   # the title of every alert; same as appName in app/capacitor.config.json

BASE_URL = "https://www.38.co.kr/html/fund/"

from datetime import timedelta, timezone

KST = timezone(timedelta(hours=9))  # fixed offset: Windows lacks a tz database by default

# Keep delayed workflow runs from waking users overnight (KST).
QUIET_START = 22
QUIET_END = 7

K_NEIGHBORS = 10
RIDGE_ALPHA = 1.0
RETURN_MIN = -0.40
RETURN_MAX = 3.00
EVAL_TEST_RATIO = 0.3
MIN_TRAIN = 30
MIN_VALID_DIMS = 3

LOGIT_ALPHA = 3.0
CONFLICT_FLAGS = 4  # this many risk signals but an upbeat prediction -> tell the user they disagree
PROB_CLIP = 0.02
SELECT_MIN_COVERAGE = 0.5
SELECT_MAX_FEATURES = 8
SELECT_MIN_GAIN = 0.003
SELECT_CHUNK = 5

WARN_RECALL = 0.7          # warning threshold must catch this share of declines on the validation window
RECENT_FROM = "2023-05-01" # price models and the pre-subscription model learn from listings after this date

LEDGER_START = "2026-11-18"   # predictions are recorded (and scored) only for stocks first predicted on or after this date
LEDGER_MIN_DOWNS = 10         # fewer resolved declines than this: the score is "too early to judge"
