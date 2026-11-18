# 안드로이드 앱 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (또는 subagent-driven-development). Steps use checkbox (`- [ ]`) syntax.

**Goal:** 지금 웹 달력을 담은 안드로이드 앱을 만들어, 증권사 버튼이 앱을 직접 실행하게 한다.

**Architecture:** `app/`에 Capacitor 프로젝트를 둔다. 앱은 `https://egoist-yun.github.io/ipo-alert/`를 `server.url`로 띄우고, 웹 화면의 `brokers.js`가 앱 안(`window.Capacitor`)이면 `@capacitor/app-launcher`로 패키지를 직접 실행한다. 웹 화면은 계속 GitHub Pages에서 갱신된다.

**Tech Stack:** Capacitor, `@capacitor/app-launcher`, Gradle(Android Studio SDK·JDK), JS(`node --test`)

**Spec:** `docs/superpowers/specs/2026-11-18-android-app-design.md`

## Global Constraints

- 앱 이름 `공모주 달력`, appId `io.github.egoistyun.ipoalert`. 폴더는 `app/`.
- 증권사 패키지는 `web/brokers.js`의 `BROKER_APPS` 12개 그대로(추측 금지). 매니페스트 `<queries>`에도 같은 12개.
- 웹 화면의 일반 브라우저 동작(intent 링크)은 유지한다.
- 서명은 디버그 서명. 릴리스 서명 키를 만들거나 저장하지 않는다.
- `app/` 빌드 산출물(`node_modules`, `android/build`, `android/.gradle`)은 커밋하지 않는다.

## Review Focus

1. 앱 안에서 모르는 증권사 → 검색 링크. 앱 안에서 앱이 없음 → 플레이스토어 앱 페이지.
2. 일반 브라우저 → 지금 동작(intent) 그대로.
3. `window.Capacitor`가 없는 환경(PC·테스트) → 예외 없음.
4. `<queries>`에 12개가 모두 들어 있음.
5. 인터넷이 없을 때 앱이 빈 화면으로 죽지 않음.

---

### Task 1: 버튼 동작 선택 함수 (`web/brokers.js`)

**Files:** Modify `web/brokers.js`, `web/brokers.test.js`, `web/app.js`

**Interfaces (Produces):**
- `brokerAction(link: {name, href, verified}, native: boolean) -> {type: 'launch', url: string, fallback: string} | {type: 'link', href: string}` — `native && verified`이면 `launch`(`url`=`<pkg>` 실행용 패키지 URL `android-app://<pkg>`, `fallback`=`market://details?id=<pkg>`); 그 외 `link`(href 그대로: 일반 브라우저 intent 또는 검색).
- `isNativeApp(win: object) -> boolean` — `win?.Capacitor?.isNativePlatform?.() === true`.
- `brokerLinks`의 반환에 `pkg: string | null` 추가.

- [ ] **Step 1: 실패하는 테스트** — `brokerAction`: 앱 안+확인된 증권사 → `launch`, `url`이 `android-app://com.eugenefn.smartchampion2`, `fallback`이 `market://details?id=com.eugenefn.smartchampion2`; 앱 안+모르는 증권사 → `link`(검색); 앱 아님 → `link`(intent). `isNativeApp({})`, `isNativeApp(undefined)` false, `Capacitor.isNativePlatform: () => true` true. `brokerLinks(['유진증권'])[0].pkg`.
- [ ] **Step 2: 실패 확인** — `node --test web/brokers.test.js`
- [ ] **Step 3: 구현** — 위 시그니처. `app.js`는 앱 안일 때 버튼 클릭을 가로채 `AppLauncher.openUrl`로 실행하고 실패 시 `fallback`을 연다(`window.Capacitor.Plugins.AppLauncher`).
- [ ] **Step 4: 통과 확인**, **Step 5: Commit** — `feat: native broker launch action`

### Task 2: Capacitor 프로젝트와 APK 빌드

**Files:** Create `app/` (package.json, capacitor.config.ts, android/…, `www/index.html`), Modify `.gitignore`

- [ ] **Step 1: 프로젝트 생성** — `app/`에서 `npm init -y`, `npm i @capacitor/core @capacitor/cli @capacitor/android @capacitor/app-launcher`, `npx cap init "공모주 달력" io.github.egoistyun.ipoalert --web-dir www`, `www/index.html`(인터넷이 없을 때 보여줄 안내만), `capacitor.config.ts`에 `server.url`, `server.cleartext false`, `npx cap add android`, `npx cap sync android`.
- [ ] **Step 2: 매니페스트** — `android/app/src/main/AndroidManifest.xml`에 `<queries><package android:name="…"/>…</queries>` 12개. 검증: `grep -c '<package android:name' …` = 12.
- [ ] **Step 3: 앱 이름·아이콘** — `strings.xml` app_name, `web/icon.svg`를 PNG(mipmap)로 변환해 교체.
- [ ] **Step 4: 빌드** — `JAVA_HOME`·`ANDROID_HOME` 설정 후 `android/gradlew assembleDebug`. Expected: `BUILD SUCCESSFUL`, `app-debug.apk` 존재.
- [ ] **Step 5: Commit** — `feat: capacitor android app`

### Task 3: 배포

- [ ] **Step 1:** 웹 변경(Task 1)을 push·배포(워크플로), 배포된 `brokers.js`에 `brokerAction` 확인.
- [ ] **Step 2:** APK를 `gh release create`로 올릴지 사용자에게 확인한 뒤(공개 업로드) 올린다. 사용자가 직접 옮긴다고 하면 파일 경로만 알려준다.
- [ ] **Step 3:** 설치·실행 확인은 사용자에게 안내한다(폰에서 직접).
