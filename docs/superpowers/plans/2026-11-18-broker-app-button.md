# 증권사 앱 열기 버튼 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 청약이 끝나지 않은 종목의 상세 화면에서 주관 증권사 앱을 버튼 하나로 연다(안드로이드).

**Architecture:** 순수 함수 모듈 `web/brokers.js`가 증권사 이름 정규화, 링크 생성, 표시 조건을 맡고, `web/app.js`가 상세 화면에 버튼을 그린다. 서버(파이썬) 쪽 변경은 없다.

**Tech Stack:** 순수 JS(ES module), `node --test`

**Spec:** `docs/superpowers/specs/2026-11-18-broker-app-button-design.md`

## Global Constraints

- 확인된 12곳의 패키지명은 설계 문서 표 그대로 쓴다. 추측한 패키지명을 추가하지 않는다.
- 확인된 곳: `intent://#Intent;package=<pkg>;S.browser_fallback_url=<encodeURIComponent("https://play.google.com/store/apps/details?id=<pkg>")>;end`
- 모르는 곳: `market://search?q=<encodeURIComponent(증권사 이름)>&c=apps`
- 버튼 문구: `<증권사 이름> 앱 열기`. 비안드로이드 안내 문구: `증권사 앱 열기는 안드로이드에서 할 수 있어요.`
- 디자인은 DESIGN.md: 기존 `.btn-medium`(38px, 연한 파랑)만 쓴다.

## Review Focus

1. 이름 변형(`한국투자증권㈜`, 공백, `케이비증권`, `엔에이치투자증권`, `유진증권`) → 같은 증권사로 인식. (Task 1 테스트)
2. 모르는 증권사 → intent가 아니라 검색 링크. (Task 1)
3. 주관사 중복·빈 이름 → 버튼 중복 없음. (Task 1)
4. 청약 마감일이 지났거나 날짜가 없음 → 버튼 없음. (Task 1)
5. PC·아이폰 → 버튼 대신 안내 문구. (Task 1 `isAndroid`)

---

### Task 1: `web/brokers.js`

**Files:** Create `web/brokers.js`, `web/brokers.test.js`

**Interfaces (Produces):**
- `normalizeBroker(name: string) -> string` — 공백·`(주)`·`㈜` 제거, 별칭(`케이비`→`KB`, `엔에이치`→`NH`, `아이비케이`→`IBK`, `유진증권`→`유진투자증권`, `미래에셋대우`→`미래에셋증권`) 적용.
- `brokerLinks(underwriters: string[]) -> {name, href, verified}[]` — 정규화한 이름 기준 중복 제거, 순서 유지.
- `showBrokerButtons(ipo, todayIso: string) -> boolean` — `ipo.sub_end`가 있고 `>= todayIso`, 스팩 아님.
- `isAndroid(userAgent: string) -> boolean`

- [ ] **Step 1: 실패하는 테스트** — 한국투자증권㈜ → verified, href가 `intent://#Intent;package=com.truefriend.neosmartarenewal;S.browser_fallback_url=https%3A%2F%2Fplay.google.com%2Fstore%2Fapps%2Fdetails%3Fid%3Dcom.truefriend.neosmartarenewal;end`; `케이비증권`→KB 패키지; `신영증권` → verified false, href `market://search?q=%EC%8B%A0%EC%98%81%EC%A6%9D%EA%B6%8C&c=apps`; `['NH투자증권','엔에이치투자증권','']` → 1개; `showBrokerButtons` 마감 전/당일 true, 지남·없음·스팩 false; `isAndroid` 안드로이드 크롬 UA true, 아이폰·윈도 false.
- [ ] **Step 2: 실패 확인** — `node --test web/brokers.test.js` / FAIL (모듈 없음)
- [ ] **Step 3: 구현**
- [ ] **Step 4: 통과 확인** — PASS
- [ ] **Step 5: Commit** — `feat: broker app links`

### Task 2: 상세 화면 버튼

**Files:** Modify `web/app.js`

- [ ] **Step 1: 구현** — `renderDetail`에서 청약 줄 다음에 `showBrokerButtons(ipo, kstToday())`이면: 안드로이드면 `brokerLinks(ipo.underwriters)`마다 `<a class="btn-medium" href=...>`(가로로 감싸는 `.broker-buttons` 영역, 간격 8px), 아니면 안내 문구(`.note`).
- [ ] **Step 2: 브라우저 확인** — 로컬 서버에서 모바일(안드로이드 UA) 크기로 유캐스트(`#2352`): 버튼 2개(유진 intent, 신영 search), PC 크기: 안내 문구, 상장한 종목(넥스아이): 버튼 없음.
- [ ] **Step 3: 전체 테스트 후 Commit·push·배포 확인** — `node --test web/` 파일들, `python -m pytest -q`, 워크플로 실행 후 배포된 `brokers.js` 확인.
