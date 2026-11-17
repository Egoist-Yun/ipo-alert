# 공모주 위험 신호 달력 + 알림 + 첫날 예측 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 38커뮤니케이션의 공모주 데이터를 하루 2번 모아 위험 신호와 첫날 가격 예측을 계산하고, 스마트폰 웹앱 달력과 ntfy 푸시 알림으로 보여준다.

**Architecture:** Python 패키지 `ipo/`가 수집 → 해석 → 신호 계산 → 예측 → 알림을 맡고 결과를 `data/*.json`에 쓴다. GitHub Actions가 이를 하루 2번 실행해 커밋하고, 정적 웹앱 `web/`과 `data/ipos.json`을 GitHub Pages로 배포한다. 웹앱은 프레임워크 없는 HTML/JS다.

**Tech Stack:** Python 3.12(Actions) / 3.14(로컬), requests, beautifulsoup4, numpy, pytest · 순수 HTML/CSS/JS, `node --test`(Node 24) · GitHub Actions, GitHub Pages · ntfy.sh

**Spec:** `docs/superpowers/specs/2026-11-17-ipo-risk-alert-design.md`

## Global Constraints

- 데이터 출처는 38커뮤니케이션뿐: `https://www.38.co.kr/html/fund/index.htm?o=k`(청약 일정), `?o=r1`(수요예측 결과), `?o=nw`(신규상장), `/html/fund/?o=v&no=<번호>`(상세). 페이지는 EUC-KR로 디코드한다.
- 요청 사이 1초 이상 간격. User-Agent는 `Mozilla/5.0 (compatible; ipo-alert/1.0)`. 개인 정보를 요청에 넣지 않는다.
- 종목은 상세 페이지 번호 `no`(정수)로 식별한다. 이름으로 합치지 않는다.
- 모든 날짜·"전날" 판정은 KST(`Asia/Seoul`) 기준.
- 스팩(이름에 `스팩` 포함)은 달력에 표시하되 신호 점수·예측을 매기지 않는다.
- 값이 없는 신호는 ⚠로 세지 않고 `flag = None`("확인 불가")로 둔다.
- 초기 신호 기준(모두 `ipo/config.py` 한 곳에): 확정가 ≤ 희망 하단 / 기관 경쟁률 < 300 / 확약 < 5% / 하단 미만 신청 ≥ 20% / 유통가능물량 ≥ 35% / 최근 비스팩 상장 10종목 중 5개 이상 첫날 종가 < 공모가.
- 예측 대상 = 첫날 종가 ÷ 공모가 − 1. 예측값은 [−0.40, +3.00]으로 자른다.
- 비교 기준(baseline)보다 평균 오차가 작지 않은 예측 방식은 화면·알림에 내보내지 않는다.
- **디자인 기준은 `C:\공모주\DESIGN.md`(토스 TDS Mobile)다.** 화면(`web/`)을 만들거나 고칠 때마다 먼저 읽는다. 값은 이 파일의 것만 쓰고 임의로 만들지 않는다:
  - 색: 강조 `#3182f6`, 배경 `#ffffff`, 제목 `#191f28`, 본문 `#4e5968`, 보조 `#8b95a1`, 면 `#f2f4f6`, 경계 `#e5e8eb`, 연한 파랑 `#e8f3ff`/`#1b64da`, 위험 `#e42939`. CSS 변수로 한 곳에 정의한다.
  - 글꼴 스택: `"Toss Product Sans", "IBM Plex Sans", "Pretendard Variable", "Noto Sans KR", sans-serif`. 토스 글꼴은 재배포 권리가 없으므로 설치하지 않고, Pretendard Variable은 웹폰트(jsDelivr)로 불러온다.
  - 글자 크기: 본문 16/24, 작은 글 14/21, 제목은 DESIGN.md의 t1~t7·st 값. 사용자 글자 크기 설정을 따르도록 `rem`을 쓴다.
  - 간격 4·6·8·16·24·32px, 버튼 크기·모서리는 DESIGN.md 표(스마트폰용 xlarge 56px/16px, 연한 파랑 버튼은 weak 스타일).
  - 누름 효과는 `scale(0.96)`, 키보드 포커스는 `0 0 0 1px #8ac0ff, 0 0 0 3px #b8d9ff`. 마우스 올림(hover) 색 변화는 만들지 않는다.
  - 그림자·모션 수치는 정해진 값이 없으므로 쓰지 않고(평면 색 층으로 구분), 움직임은 `prefers-reduced-motion`을 따른다.
  - DESIGN.md에 없는 부품(달력, 막대, 상세 패널)은 "확장"이다. 위 토큰만 조합해 만들고 코드 주석에 `/* extension: not in TDS */`로 표시한다. 일반 핀테크 관습으로 카드·그림자·탭·토스트·다이얼로그를 새로 만들지 않는다.
  - 흰 글자 on `#3182f6`는 대비 3.71:1(AA 미달)이라고 DESIGN.md가 밝혔다. 작은 글자는 연한 파랑 배경+`#1b64da` 조합을 쓰고, 파란 채움 버튼 글자는 17px/600 이상일 때만 쓴다.
  - 말투는 DESIGN.md "Voice & Tone": 짧고 직접적으로, 결과와 다음 행동을 분명하게, 안심시키는 빈말 금지.
- 화면 하단 고정 문구(정확히): `투자 권유가 아닌 공개 정보 정리입니다. 청약 판단은 본인이 하세요.`
- 수집 실패 시 기존 `data/ipos.json`을 빈 데이터로 덮어쓰지 않는다.

## Review Focus

1. **사이트가 200을 주지만 표가 비어 있음(구조 변경·차단)** → 실패 알림 1건, 기존 `ipos.json` 유지. (Task 8 테스트)
2. **같은 종목이 표마다 이름이 다름**(`에스에프씨(유가)`, `영광(구.영광공작소)`) → `no`로 합쳐 한 종목으로 나와야 함. (Task 2 테스트)
3. **공모가·경쟁률·확약이 `-`이거나 빈 칸** → 예외 없이 `None`. (Task 2, 3 테스트)
4. **같은 날 두 번 실행·재실행** → 같은 알림이 두 번 가지 않음. (Task 7 테스트)
5. **청약이 월말을 넘김**(11/27~11/30) → 달력 두 달 모두에 막대가 나오고, 전날 알림은 11/26. (Task 7, 9 테스트)

---

## 공통 데이터 형태

`ipo/models.py`의 `Ipo`(dataclass, `asdict`로 JSON 저장). 모든 Task가 이 이름을 쓴다.

```python
@dataclass
class Ipo:
    no: int
    name: str
    url: str
    market: str | None = None            # "코스닥" | "유가증권" | "코넥스"
    industry: str | None = None
    is_spac: bool = False
    is_bio: bool = False                  # industry에 의약|의학|생물|바이오 포함
    sub_start: str | None = None          # "YYYY-MM-DD"
    sub_end: str | None = None
    listing_date: str | None = None
    band_low: int | None = None
    band_high: int | None = None
    final_price: int | None = None
    underwriters: list[str] = field(default_factory=list)
    offer_amount_mil: int | None = None   # 백만원
    inst_competition: float | None = None # 66.58
    lockup_pct: float | None = None       # 0.06
    below_band_pct: float | None = None   # 48.15
    float_pct: float | None = None        # 36.97
    open_price: int | None = None
    first_close: int | None = None
    signals: list[dict] = field(default_factory=list)  # {"key","label","value","flag"}
    flag_count: int = 0
    unknown_count: int = 0
    prediction: dict | None = None
```

`first_day_return(ipo) -> float | None` = `first_close / final_price - 1` (둘 중 하나라도 없으면 None).

## 파일 구조

```
ipo/__init__.py
ipo/models.py       Ipo, first_day_return
ipo/config.py       신호 기준값, 예측 설정, 문구
ipo/fetch.py        get_html(url) — 간격·인코딩
ipo/parse.py        표 3종 + 상세 페이지 해석
ipo/collect.py      표 + 상세를 합쳐 list[Ipo]
ipo/signals.py      신호 계산
ipo/history.py      과거 종목 수집, 신호 백테스트 표
ipo/predict.py      비슷한 종목, 모델, 검증
ipo/notify.py       ntfy 전송, 알림 판정, 상태
ipo/main.py         전체 실행
tests/fixtures/     저장한 HTML 견본
tests/test_*.py
web/index.html, web/style.css, web/app.js, web/calendar.js, web/manifest.json
web/calendar.test.js
.github/workflows/update.yml, .github/workflows/probe.yml
data/ipos.json, data/history.json, data/state.json, data/backtest.md
requirements.txt, .gitignore, README.md
```

---

### Task 1: 저장소 준비와 클라우드 접속 확인

설계 5절 위험 1번을 가장 먼저 확인한다. 이 결과가 Task 10의 실행 위치를 정한다.

**Files:**
- Create: `requirements.txt`(`requests`, `beautifulsoup4`, `numpy`, `pytest`), `.gitignore`(`__pycache__/`, `.venv/`), `.github/workflows/probe.yml`, `ipo/__init__.py`

- [ ] **Step 1: git 저장소 만들기**

Run: `git init -b main` (in `C:\공모주`)
Expected: `Initialized empty Git repository`

- [ ] **Step 2: `probe.yml` 작성** — `workflow_dispatch`로만 실행. ubuntu-latest에서 `curl -sS -A "Mozilla/5.0 (compatible; ipo-alert/1.0)" -o page.html -w "%{http_code}" "https://www.38.co.kr/html/fund/index.htm?o=k"` 후 `iconv -f euc-kr -t utf-8 page.html | grep -c "공모주일정"`을 출력한다.

- [ ] **Step 3: 사용자와 GitHub 공개 저장소 생성 후 push** — 사용자가 GitHub에 로그인하고 저장소(`ipo-alert`, 공개)를 만든다. 비밀번호·인증 코드는 사용자가 입력한다.

```bash
git add -A
git commit -m "chore: project skeleton and connectivity probe"
git remote add origin https://github.com/<계정>/ipo-alert.git
git push -u origin main
```

- [ ] **Step 4: probe 실행 결과 확인**

Run: `gh workflow run probe.yml` 후 `gh run watch`
Expected: HTTP `200`, grep 결과 `1` 이상. 결과를 사용자에게 보고하고 **실패하면** Task 10에서 "로컬 수집 모드"(10-B)를 쓴다고 기록한다.

---

### Task 2: 목록 표 3종 해석

**Files:**
- Create: `ipo/models.py`, `ipo/fetch.py`, `ipo/parse.py`, `tests/fixtures/{schedule,demand,listing}.html`, `tests/test_parse_tables.py`

**Interfaces:**
- Produces:
  - `get_html(url: str) -> str` — 마지막 요청과 1초 이상 간격, `requests` 응답 바이트를 `euc-kr`(errors="replace")로 디코드, 실패 시 `FetchError`.
  - `parse_schedule(html) -> list[dict]` — 키: `no, name, sub_start, sub_end, final_price, band_low, band_high, underwriters`
  - `parse_demand(html) -> list[dict]` — 키: `no, name, inst_competition, lockup_pct, final_price, offer_amount_mil`
  - `parse_listing(html) -> list[dict]` — 키: `no, name, listing_date, final_price, open_price, first_close`
  - 표에서 행이 0개면 `ParseError`.

- [ ] **Step 1: 견본 저장** — `python -c` 한 줄로 `get_html`을 쓰지 말고(아직 없음) `requests`로 세 URL을 받아 원본 바이트 그대로 `tests/fixtures/`에 저장한다. 저장 후 파일 3개가 각각 10KB 이상인지 확인.

- [ ] **Step 2: 실패하는 테스트 작성** (`tests/test_parse_tables.py`, 견본은 바이트로 읽어 euc-kr 디코드)

```python
def test_schedule_nexi():
    rows = {r["name"]: r for r in parse_schedule(load("schedule.html"))}
    r = rows["넥스아이"]
    assert r["no"] == 2336
    assert (r["sub_start"], r["sub_end"]) == ("2026-11-03", "2026-11-04")
    assert (r["band_low"], r["band_high"], r["final_price"]) == (10500, 13000, 8000)
    assert r["underwriters"] == ["한국투자증권"]

def test_schedule_missing_price_is_none():          # Review Focus 3
    r = next(r for r in parse_schedule(load("schedule.html")) if r["name"] == "제논")
    assert r["final_price"] is None

def test_demand_nexi_and_missing_lockup():
    rows = {r["name"]: r for r in parse_demand(load("demand.html"))}
    assert rows["넥스아이"]["inst_competition"] == 66.58
    assert rows["넥스아이"]["lockup_pct"] == 0.06
    assert rows["엠비디"]["lockup_pct"] is None      # "-"

def test_listing_nexi():
    r = next(r for r in parse_listing(load("listing.html")) if r["name"] == "넥스아이")
    assert (r["listing_date"], r["open_price"], r["first_close"]) == ("2026-11-12", 7620, 4810)

def test_same_stock_different_names_share_no():   # Review Focus 2
    sched = {r["no"] for r in parse_schedule(load("schedule.html")) if r["name"].startswith("에스에프씨")}
    assert len(sched) == 1

def test_empty_table_raises():                     # Review Focus 1
    with pytest.raises(ParseError):
        parse_schedule("<html><body><table></table></body></html>")
```

- [ ] **Step 3: 실패 확인** — Run: `pytest tests/test_parse_tables.py -v` / Expected: FAIL (import error)

- [ ] **Step 4: `ipo/models.py`(위 공통 형태), `ipo/fetch.py`, `ipo/parse.py` 구현** — BeautifulSoup으로 헤더에 `종목명`/`기업명`이 있는 표를 찾는다. `no`는 행 안 링크의 `no=` 값. 숫자는 `,`·`원`·`:1`·`%` 제거 후 변환, `-`·빈칸은 None. 날짜 `2026.11.03` / `2026/11/12` 모두 `YYYY-MM-DD`로. 신규상장 표에 링크가 없으면 `no`를 None으로 두고 이름 정규화(`(유가)`, `(구.…)` 제거)를 Task 4의 합치기에서 보조 키로 쓴다.

- [ ] **Step 5: 통과 확인** — Run: `pytest tests/test_parse_tables.py -v` / Expected: 6 passed

- [ ] **Step 6: Commit** — `git add ipo tests && git commit -m "feat: parse schedule, demand, listing tables"`

---

### Task 3: 상세 페이지 해석

**Files:**
- Create: `tests/fixtures/detail_2336.html`(넥스아이), `tests/fixtures/detail_2352.html`(유캐스트), `tests/test_parse_detail.py`
- Modify: `ipo/parse.py`

**Interfaces:**
- Produces: `parse_detail(html: str) -> dict` — 키: `market, industry, band_low, band_high, final_price, offer_amount_mil, sub_start, sub_end, listing_date, inst_competition, lockup_pct, below_band_pct, float_pct`. 찾지 못한 키는 None.

- [ ] **Step 1: 견본 저장** — 두 상세 페이지를 바이트 그대로 저장.

- [ ] **Step 2: 실패하는 테스트 작성**

```python
def test_detail_nexi():
    d = parse_detail(load("detail_2336.html"))
    assert d["market"] == "코스닥"
    assert "의학" in d["industry"]
    assert d["listing_date"] == "2026-11-12"
    assert d["offer_amount_mil"] == 40000
    assert d["below_band_pct"] == 48.15          # "10,500원(하단) 미만" 행의 비율
    assert 36.0 <= d["float_pct"] <= 38.0        # 공모 후 유통가능 물량 합계 비율

def test_detail_missing_sections_are_none():     # Review Focus 3
    d = parse_detail("<html><body>종목명 X</body></html>")
    assert d["below_band_pct"] is None and d["float_pct"] is None
```

- [ ] **Step 3: 실패 확인** — `pytest tests/test_parse_detail.py -v` / FAIL

- [ ] **Step 4: `parse_detail` 구현** — 라벨 셀(`시장구분`, `업종`, `희망공모가액`, `확정공모가`, `공모금액`, `공모청약일`, `상장일`, `기관경쟁률`, `의무보유확약`) 옆 셀 값을 읽는다. 하단 미만 비율은 `(하단) 미만`이 든 행의 마지막 `%` 값. 유통가능물량은 `유통가능 물량` 표의 합계 행 비율. 표 형식이 달라 못 찾으면 None(예외 금지).

- [ ] **Step 5: 통과 확인** — Expected: 2 passed (넥스아이 유통 비율이 범위를 벗어나면 실제 표를 열어 합계 행 선택 로직을 고친다)

- [ ] **Step 6: Commit** — `git commit -am "feat: parse IPO detail page"` (새 파일은 `git add` 먼저)

---

### Task 4: 수집 합치기와 위험 신호

**Files:**
- Create: `ipo/config.py`, `ipo/collect.py`, `ipo/signals.py`, `tests/test_signals.py`, `tests/test_collect.py`

**Interfaces:**
- Consumes: Task 2·3의 `parse_*`, `get_html`, `Ipo`
- Produces:
  - `collect_current(fetch=get_html) -> list[Ipo]` — 표 3종을 `no`로 합치고, 수요예측 결과가 있거나 청약 시작이 오늘 이후인 종목만 상세 페이지를 받는다. 이미 받은 상세는 `cache: dict[int, dict]` 인자로 재사용.
  - `market_mood(history: list[Ipo], before: str) -> float | None` — `before` 이전 상장 비스팩 최근 10종목 중 첫날 종가 < 공모가 비율. 10개 미만이면 None.
  - `score(ipo: Ipo, mood: float | None) -> Ipo` — `signals`, `flag_count`, `unknown_count`를 채운 사본. 스팩이면 `signals=[]`.

- [ ] **Step 1: `config.py` 작성** — Global Constraints의 기준값을 상수로: `PRICE_AT_OR_BELOW_LOW=True`, `MIN_INST_COMPETITION=300`, `MIN_LOCKUP_PCT=5.0`, `MAX_BELOW_BAND_PCT=20.0`, `MAX_FLOAT_PCT=35.0`, `MOOD_WINDOW=10`, `MOOD_BAD_RATIO=0.5`, 그리고 `DISCLAIMER` 문구(정확히 Global Constraints대로).

- [ ] **Step 2: 실패하는 테스트 작성** (`tests/test_signals.py`)

```python
NEXI = Ipo(no=2336, name="넥스아이", url="", band_low=10500, band_high=13000, final_price=8000,
           inst_competition=66.58, lockup_pct=0.06, below_band_pct=48.15, float_pct=36.97)
OPTONICS = Ipo(no=1, name="옵토닉스", url="", band_low=10000, band_high=12000, final_price=12000,
               inst_competition=1201.81, lockup_pct=5.62, below_band_pct=None, float_pct=None)

def test_nexi_has_at_least_4_flags():
    assert score(NEXI, mood=None).flag_count >= 4

def test_good_ipo_has_at_most_1_flag():
    assert score(OPTONICS, mood=0.2).flag_count <= 1

def test_missing_values_are_unknown_not_flagged():
    s = score(OPTONICS, mood=None)
    assert s.unknown_count == 3            # below_band, float, mood
    assert all(sig["flag"] is None for sig in s.signals if sig["value"] is None)

def test_boundaries():
    s = score(replace(NEXI, inst_competition=300, lockup_pct=5.0, below_band_pct=20.0, float_pct=35.0), None)
    flags = {x["key"]: x["flag"] for x in s.signals}
    assert flags["inst_competition"] is False and flags["lockup"] is False
    assert flags["below_band"] is True and flags["float"] is True

def test_spac_not_scored():
    assert score(Ipo(no=9, name="신영스팩12호", url="", is_spac=True), None).signals == []
```

`tests/test_collect.py`: 가짜 `fetch`(URL → 견본 HTML 사전)로 `collect_current`를 돌려 넥스아이가 한 번만 나오고 `inst_competition == 66.58`, `final_price == 8000`인지, `market_mood`가 10개 미만이면 None인지 확인.

- [ ] **Step 3: 실패 확인** — `pytest tests/test_signals.py tests/test_collect.py -v` / FAIL

- [ ] **Step 4: 구현** — 신호 키와 라벨: `price_position`(공모가 위치), `inst_competition`(기관 경쟁률), `lockup`(의무보유확약), `below_band`(하단 미만 신청), `float`(유통가능물량), `mood`(최근 시장 분위기). `is_spac`은 이름에 `스팩`, `is_bio`는 업종 정규식 `의약|의학|생물|바이오`.

- [ ] **Step 5: 통과 확인** — Expected: all passed

- [ ] **Step 6: Commit** — `git commit -m "feat: merge tables and compute risk signals"`

---

### Task 5: 과거 종목 수집과 신호 백테스트

**Files:**
- Create: `ipo/history.py`, `tests/test_history.py`, `data/history.json`, `data/backtest.md`

**Interfaces:**
- Consumes: `parse_listing`, `parse_detail`, `get_html`, `score`, `market_mood`
- Produces:
  - `build_history(pages: int, fetch=get_html) -> list[Ipo]` — 신규상장 표 1~`pages`쪽에서 첫날 종가가 있는 종목을 모으고 상세를 받아 채운다.
  - `update_history(existing: list[Ipo], fetch=get_html) -> list[Ipo]` — 1쪽만 보고 새 종목만 추가.
  - `signal_backtest(history: list[Ipo]) -> str` — 마크다운 표: 신호 개수(0~6)별 종목 수, 첫날 종가 < 공모가 비율, 첫날 등락률 가운데 값. 각 종목의 `mood`는 그 종목 상장일 이전 데이터만으로 계산.
  - `load_history(path) -> list[Ipo]`, `save_history(path, items)`

- [ ] **Step 1: 실패하는 테스트 작성** — 가짜 데이터 6종목으로 `signal_backtest` 결과 문자열에 `| 0 |`, `| 4 |` 행과 올바른 비율(예: 신호 4개 2종목 중 2개 하락 → `100%`)이 있는지, `update_history`가 이미 있는 `no`를 다시 추가하지 않는지 확인.

- [ ] **Step 2: 실패 확인** — `pytest tests/test_history.py -v` / FAIL

- [ ] **Step 3: 구현** — 스팩 제외. 첫날 종가 없는 종목 제외.

- [ ] **Step 4: 통과 확인** — Expected: passed

- [ ] **Step 5: 실제 과거 데이터 1회 수집 (로컬, 약 10분)**

Run: `python -c "from ipo.history import *; save_history('data/history.json', build_history(19))"`
Expected: `data/history.json`에 비스팩 250종목 이상. 넥스아이 `first_close == 4810`.

- [ ] **Step 6: 백테스트 표 생성 후 사용자에게 보고**

Run: `python -c "from ipo.history import *; open('data/backtest.md','w',encoding='utf-8').write(signal_backtest(load_history('data/history.json')))"`
Expected: 신호 개수가 많을수록 하락 비율이 대체로 높아지는 표. 그렇지 않은 신호가 있으면 표를 사용자에게 보여주고 `config.py` 기준값 변경 여부를 묻는다(사용자 결정).

- [ ] **Step 7: Commit** — `git add ipo/history.py tests/test_history.py data && git commit -m "feat: collect history and backtest signals"`

---

### Task 6: 첫날 가격 예측

**Files:**
- Create: `ipo/predict.py`, `tests/test_predict.py`
- Modify: `ipo/config.py` (`K_NEIGHBORS=10`, `RIDGE_ALPHA=1.0`, `RETURN_MIN=-0.40`, `RETURN_MAX=3.00`, `EVAL_TEST_RATIO=0.3`)

**Interfaces:**
- Consumes: `Ipo`, `first_day_return`, `market_mood`
- Produces:
  - `features(ipo: Ipo, mood: float | None) -> list[float | None]` — 순서 고정: `log(inst_competition)`, `lockup_pct`, 공모가 위치 `(final-low)/(high-low)`(밴드 폭 0이면 None), `below_band_pct`, `float_pct`, `mood`, `log(offer_amount_mil)`, 유가증권 여부(1/0), `is_bio`(1/0).
  - `neighbors(target: Ipo, history: list[Ipo], k: int) -> list[Ipo]` — 학습 데이터 기준 평균·표준편차로 표준화, 둘 다 값이 있는 차원만으로 평균 제곱거리(유효 차원 3개 미만인 후보는 제외).
  - `knn_summary(nbrs: list[Ipo], final_price: int) -> dict` — `{"median","p25","p75","down_count","n","price_low","price_high","items":[{"no","name","return"}]}`; 가격은 `final_price*(1+p25)`, `final_price*(1+p75)`를 자르기 후 원 단위 반올림.
  - `fit_ridge(history) -> Model`, `Model.predict(ipo, mood) -> float` — 결측은 학습 데이터 중앙값으로 채움, numpy로 ridge 닫힌 해.
  - `evaluate(history) -> dict` — 상장일 순 정렬, 뒤 30%를 한 종목씩 그 이전 종목만으로 예측(walk-forward). 방식 `knn`(이웃 중앙값), `model`, `baseline`(이전 종목 등락률 중앙값)마다 `{"mae","direction_acc","n"}`. `direction_acc` = (예측<0) == (실제<0) 비율.
  - `predict_for(ipo, history, eval_result) -> dict | None` — `{"knn": {...} | None, "model": {"return","mae"} | None, "accuracy": eval_result}`. 해당 방식 `mae >= baseline.mae`이면 그 방식은 None. 스팩이거나 `final_price`·`inst_competition`이 없으면 None.

- [ ] **Step 1: 실패하는 테스트 작성**

```python
def test_clip_range():
    assert clip_return(5.0) == 3.00 and clip_return(-0.9) == -0.40

def test_neighbors_prefers_similar():
    hist = [mk(no=i, comp=60+i, lock=0.1, ret=-0.3) for i in range(5)] + \
           [mk(no=100+i, comp=1200+i, lock=10, ret=0.8) for i in range(5)]
    nb = neighbors(mk(no=999, comp=65, lock=0.1, ret=None), hist, k=5)
    assert {n.no for n in nb} == set(range(5))

def test_neighbors_ignore_missing_dims():
    t = mk(no=999, comp=65, lock=None, ret=None)
    assert len(neighbors(t, [mk(no=1, comp=60, lock=0.1, ret=-0.2)] * 3, k=3)) == 3

def test_knn_summary_counts_down():
    s = knn_summary([mk(no=i, ret=r) for i, r in enumerate([-0.3, -0.1, 0.2])], final_price=10000)
    assert s["down_count"] == 2 and s["n"] == 3

def test_method_hidden_when_not_better_than_baseline():
    ev = {"knn": {"mae": 0.30}, "model": {"mae": 0.20}, "baseline": {"mae": 0.25}}
    p = predict_for(NEXI_WITH_PRICE, HIST, ev)
    assert p["knn"] is None and p["model"] is not None

def test_evaluate_uses_only_past():
    # 미래 종목 등락률을 극단값으로 바꿔도 첫 평가 종목의 baseline 예측이 바뀌지 않아야 함
```

- [ ] **Step 2: 실패 확인** — `pytest tests/test_predict.py -v` / FAIL

- [ ] **Step 3: 구현**

- [ ] **Step 4: 통과 확인** — Expected: passed

- [ ] **Step 5: 실제 데이터로 검증 결과를 `data/backtest.md`에 덧붙이고 사용자에게 보고**

Run: `python -m ipo.predict --report data/history.json >> data/backtest.md`
Expected: 방식별 MAE·적중률 표. 어느 방식이 baseline보다 못해 숨겨지는지 사용자에게 그대로 알린다.

- [ ] **Step 6: Commit** — `git commit -am "feat: first-day return prediction with walk-forward evaluation"`

---

### Task 7: 알림

**Files:**
- Create: `ipo/notify.py`, `tests/test_notify.py`

**Interfaces:**
- Consumes: `Ipo`(scored, prediction 포함)
- Produces:
  - `due_alerts(ipos: list[Ipo], state: dict, now_kst: datetime) -> list[tuple[str, Ipo]]` — 키 `"result:<no>"`: 비스팩이고 `inst_competition`이 생겼고 아직 안 보냄. 키 `"eve:<no>"`: `now_kst.date() == sub_start - 1일`이고 `now_kst.hour >= 12`이고 아직 안 보냄.
  - `format_alert(ipo: Ipo, site_url: str) -> dict` — ntfy JSON: `topic`은 호출 측이 채움. `title` = `"{name} ⚠{flag_count}개 · 청약 {M/D}~{M/D}"`, `message` = ⚠ 신호별 한 줄 + (있으면) `"비슷한 {n}개 중 {down}개 하락"` · `"모델 예측 {+x%} (±{mae}%p)"` + `"확인 불가 {unknown_count}개"`(0이면 생략) + DISCLAIMER, `click` = `f"{site_url}#{no}"`.
  - `send(payload: dict, topic: str, post=requests.post) -> None` — `POST https://ntfy.sh` JSON 본문(한글 제목 때문에 헤더 방식 금지).
  - `failure_alert(reason: str) -> dict` — 제목 `"공모주 수집 실패"`.
  - `load_state(path) -> dict`, `save_state(path, state)` — `{"sent": ["result:2336", ...]}`.

- [ ] **Step 1: 실패하는 테스트 작성**

```python
def test_result_alert_once():                      # Review Focus 4
    st = {"sent": []}
    first = due_alerts([NEXI_SCORED], st, kst(2026, 10, 29, 18))
    assert [k for k, _ in first] == ["result:2336"]
    mark_sent(st, first)
    assert due_alerts([NEXI_SCORED], st, kst(2026, 10, 29, 18)) == []

def test_eve_alert_across_month():                 # Review Focus 5
    ipo = replace(NEXI_SCORED, no=77, sub_start="2026-11-27", sub_end="2026-11-30")
    st = {"sent": ["result:77"]}
    assert due_alerts([ipo], st, kst(2026, 11, 26, 8)) == []      # 아침엔 아직
    assert [k for k, _ in due_alerts([ipo], st, kst(2026, 11, 26, 18))] == ["eve:77"]

def test_zero_flag_still_alerts():
    ipo = replace(NEXI_SCORED, flag_count=0)
    assert due_alerts([ipo], {"sent": []}, kst(2026, 10, 29, 18))

def test_format_contains_disclaimer_and_click():
    p = format_alert(NEXI_SCORED, "https://x.github.io/ipo-alert/")
    assert p["click"].endswith("#2336") and DISCLAIMER in p["message"]

def test_send_posts_json():
    calls = []
    send({"title": "t"}, "topic-x", post=lambda url, json, timeout: calls.append((url, json)))
    assert calls[0][0] == "https://ntfy.sh" and calls[0][1]["topic"] == "topic-x"
```

- [ ] **Step 2: 실패 확인** — `pytest tests/test_notify.py -v` / FAIL
- [ ] **Step 3: 구현**
- [ ] **Step 4: 통과 확인** — Expected: 5 passed
- [ ] **Step 5: Commit** — `git commit -m "feat: ntfy alerts with dedupe"`

---

### Task 8: 전체 실행 `ipo.main`

**Files:**
- Create: `ipo/main.py`, `tests/test_main.py`

**Interfaces:**
- Consumes: 앞 Task 전부
- Produces: `run(data_dir: Path, topic: str | None, site_url: str, now_kst: datetime, fetch=get_html, post=requests.post) -> int` — 종료 코드. 순서: history 갱신 → 현재 종목 수집 → score → 평가(history로 1회) → predict_for → 달력 범위(오늘 기준 90일 전 이후 청약) 필터 → `ipos.json` 저장(`{"updated_at": ISO KST, "disclaimer": DISCLAIMER, "ipos": [...]}`) → 알림 → state 저장. `topic`이 None이면 알림 생략(로컬 테스트용). CLI: `python -m ipo.main`이 환경변수 `NTFY_TOPIC`, `SITE_URL`을 읽는다.

- [ ] **Step 1: 실패하는 테스트 작성**

```python
def test_run_writes_ipos_json(tmp_path):            # 견본 fetch, 가짜 post
    ...; assert run(tmp_path, "t", "https://s/", kst(2026,11,17,18), fetch=fake, post=rec) == 0
    data = json.loads((tmp_path / "ipos.json").read_text("utf-8"))
    assert any(i["name"] == "유캐스트" for i in data["ipos"])

def test_failure_keeps_old_file_and_alerts(tmp_path):  # Review Focus 1
    (tmp_path / "ipos.json").write_text('{"ipos":[{"no":1}]}', "utf-8")
    code = run(tmp_path, "t", "https://s/", NOW, fetch=lambda u: "<html></html>", post=rec)
    assert code != 0
    assert json.loads((tmp_path / "ipos.json").read_text("utf-8"))["ipos"] == [{"no": 1}]
    assert rec.calls[-1]["title"] == "공모주 수집 실패"
```

- [ ] **Step 2: 실패 확인** — FAIL
- [ ] **Step 3: 구현** — 모든 예외를 잡아 `failure_alert` 전송 후 0 아닌 코드 반환. 파일 쓰기는 임시 파일 후 교체.
- [ ] **Step 4: 통과 확인 + 전체 테스트** — Run: `pytest -v` / Expected: all passed
- [ ] **Step 5: 로컬 실제 실행** — Run: `python -m ipo.main` (NTFY_TOPIC 없이) / Expected: `data/ipos.json` 생성, 유캐스트 `flag_count` 출력
- [ ] **Step 6: Commit** — `git add -A && git commit -m "feat: end-to-end run"`

---

### Task 9: 웹앱 달력

**Files:**
- Create: `web/index.html`, `web/style.css`, `web/calendar.js`, `web/app.js`, `web/manifest.json`, `web/calendar.test.js`

**Interfaces:**
- Consumes: `ipos.json` 형태(Task 8)
- Produces (`calendar.js`, ES module):
  - `monthGrid(year: number, month: number) -> string[][]` — 월요일 시작 주 배열, 칸은 `"YYYY-MM-DD"` 또는 `""`.
  - `barsForMonth(ipos, year, month) -> {no, name, start, end, flagCount, isSpac}[]` — 청약 기간이 그 달과 겹치는 종목, `start`/`end`는 그 달 안으로 자른 날짜.
  - `listForMonth(ipos, year, month)` — 청약 시작일 순.

- [ ] **Step 1: 실패하는 테스트 작성** (`node:test`)

```js
test('bar spans month boundary', () => {               // Review Focus 5
  const ipos = [{no: 77, name: 'A', sub_start: '2026-11-27', sub_end: '2026-11-30', flag_count: 2}];
  assert.deepEqual(barsForMonth(ipos, 2026, 11).map(b => [b.start, b.end]), [['2026-11-27','2026-11-30']]);
  const dec = [{...ipos[0], sub_end: '2026-12-01'}];
  assert.equal(barsForMonth(dec, 2026, 12)[0].start, '2026-12-01');
});
test('monthGrid starts Monday', () => { assert.equal(monthGrid(2026, 11)[0][6], '2026-11-01'); });
test('ipo without dates is skipped', () => { assert.equal(barsForMonth([{no:1,name:'x'}], 2026, 11).length, 0); });
```

- [ ] **Step 2: 실패 확인** — Run: `node --test web/` / FAIL
- [ ] **Step 3: `calendar.js` 구현 후 통과 확인** — Expected: 3 pass
- [ ] **Step 4: 화면 구현** (`index.html`, `app.js`, `style.css`, `manifest.json`)
  - `fetch('ipos.json')` → 이번 달 달력, ◀ ▶ 이동, 막대에 `이름 ⚠N`(스팩은 `스팩`, 결과 전은 `대기 중`).
  - 막대·목록 클릭 시 상세 패널: 청약일, 상장일, 증권사, 신호별 값과 ⚠/확인 불가, `prediction.knn`(가운데 값, 범위, 원 단위 예상 범위, 비슷한 종목 목록), `prediction.model`(값 ± mae), 과거 적중률, 원문 링크.
  - `location.hash`가 `#<no>`이면 해당 종목의 달로 이동해 상세를 연다.
  - 640px 미만에서 달력 아래 날짜순 목록 표시. 하단에 갱신 시각과 DISCLAIMER(json의 `disclaimer`).
  - 시각 디자인은 **`DESIGN.md`만 기준**으로 한다(Global Constraints의 디자인 항목). 위험 신호 ⚠는 `#e42939`, "확인 불가"는 `#8b95a1`, 신호 개수 뱃지는 TDS Badge(weak) 모양으로 만든다. 상세 패널은 달력 아래에 펼치는 영역으로 두고(바텀시트 등 미측정 부품 금지), 버튼은 xlarge 56px를 쓴다.
- [ ] **Step 5: 브라우저 확인** — `data/ipos.json`을 `web/`에 복사한 뒤 `python -m http.server -d web 8000`, 브라우저 미리보기에서 모바일 크기(375px)로: 11월에 유캐스트 막대, 클릭 시 상세, `#2352` 주소로 바로 열림, 가로 스크롤 없음.
- [ ] **Step 5-1: 디자인 기준 점검** — `web/style.css`에 DESIGN.md 밖의 색(`#` 값)·`box-shadow`·`:hover` 색 변화가 없는지 `grep`으로 확인하고, 스크린샷을 DESIGN.md와 대조해 어긋난 곳을 고친다. 점검 결과를 사용자에게 한 줄로 보고한다.
- [ ] **Step 6: Commit** — `git add web && git commit -m "feat: mobile calendar web app"` (`web/ipos.json`은 `.gitignore`에 추가)

---

### Task 10: 자동 실행과 배포, 사용자 설정

**Files:**
- Create: `.github/workflows/update.yml`, `README.md`
- Delete: `.github/workflows/probe.yml`

**10-A (Task 1 접속 성공 시)**

- [ ] **Step 1: `update.yml` 작성** — `schedule: cron "0 23 * * *"`(KST 08시), `"0 9 * * *"`(KST 18시) + `workflow_dispatch`. `concurrency: ipo-update`(Review Focus 4). 단계: Python 3.12 설치 → `pip install -r requirements.txt` → `pytest -q` → `python -m ipo.main`(env `NTFY_TOPIC: ${{ secrets.NTFY_TOPIC }}`, `SITE_URL: https://<계정>.github.io/ipo-alert/`) → `data/` 변경 커밋·push(`github-actions[bot]`) → `web/*`와 `data/ipos.json`을 `_site/`에 복사 → `actions/upload-pages-artifact` → `actions/deploy-pages`. 권한 `contents: write`, `pages: write`, `id-token: write`. `ipo.main`이 실패 코드여도 배포 단계는 기존 파일로 계속(`if: always()`).

- [ ] **Step 2: ntfy 채널 이름 만들기와 Secret 등록** — 추측 어려운 이름 생성: `python -c "import secrets; print('ipo-' + secrets.token_urlsafe(12))"`. 사용자가 GitHub 저장소 Settings → Secrets에 `NTFY_TOPIC`으로 등록(값은 대화에 다시 적지 않음). Settings → Pages → Source를 "GitHub Actions"로.

- [ ] **Step 3: 사용자 스마트폰 설정** — ntfy 앱 설치 → 같은 채널 구독 → 웹앱 주소를 홈 화면에 추가. README에 이 3단계를 적는다.

- [ ] **Step 4: 수동 실행 확인** — Run: `gh workflow run update.yml` 후 `gh run watch` / Expected: 성공, Pages 주소에서 달력 표시, 스마트폰에 결과 알림 도착. 첫 실행이라 `state.json`이 비어 있으므로 달력 범위의 결과 있는 종목마다 알림이 온다(첫 실행에서만 정상). 알림이 너무 많으면 사용자에게 알리고, 첫 실행 전에 `state.json`에 이미 상장한 종목 키를 미리 채우는 방식으로 바꾼다.

**10-B (Task 1 접속 실패 시)** — 같은 `ipo.main`을 Windows 작업 스케줄러로 08:00/18:00 실행하는 `scripts/run.ps1`(실행 → `git commit` → `git push`)을 만들고, `update.yml`은 push 시 Pages 배포만 한다. 컴퓨터가 꺼져 있으면 갱신이 멈춘다는 점을 README와 사용자에게 알린다.

- [ ] **Step 5: Commit** — `git rm .github/workflows/probe.yml && git add -A && git commit -m "ci: scheduled update, pages deploy, setup guide" && git push`
