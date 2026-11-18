# 공모주 달력 안드로이드 앱

지금 웹 달력(https://egoist-yun.github.io/ipo-alert/)을 앱 안에 띄우는 Capacitor 앱입니다.
화면과 데이터는 웹에서 갱신되므로 화면을 고쳐도 앱을 다시 설치할 필요가 없습니다.
앱 안에서는 증권사 버튼이 `@capacitor/app-launcher`로 증권사 앱을 직접 실행합니다.

## 빌드 (Windows)

필요한 것: JDK 21, Android SDK(Android Studio), Node.

1. **경로에 한글이 없는 폴더로 복사**합니다. 안드로이드 빌드 도구가 한글 경로를 거부합니다.
   `package.json`, `package-lock.json`, `capacitor.config.json`, `www`, `node_modules`, `android`
   (단 `android/.gradle`, `android/build`는 제외)를 `C:\ipo-app-build`로 복사합니다.
2. `C:\ipo-app-build\android\local.properties`에 `sdk.dir=C:/Users/<이름>/AppData/Local/Android/Sdk`를 적습니다.
3. PowerShell에서:
   ```
   $env:JAVA_HOME = 'C:\Users\<이름>\jdk21'
   $env:ANDROID_HOME = 'C:\Users\<이름>\AppData\Local\Android\Sdk'
   cd C:\ipo-app-build\android
   .\gradlew.bat assembleDebug --console=plain
   ```
4. 결과: `android\app\build\outputs\apk\debug\app-debug.apk` (디버그 서명, 개인용).

## 증권사 목록을 바꿀 때
`web/brokers.js`의 `BROKER_APPS`와 `android/app/src/main/AndroidManifest.xml`의 `<queries>`를 같이 고쳐야 합니다
(안드로이드 11 이상은 매니페스트에 적힌 패키지만 찾을 수 있습니다).

## 알아둘 점
- 화면(목록/상세/실전 성적)은 웹 주소의 해시로 전환됩니다. 폰의 뒤로가기 키가 상세에서 목록으로 가도록 `MainActivity.java`가 웹 기록 뒤로가기를 처리합니다(이 파일을 바꾸면 APK를 다시 빌드해야 합니다).
- 디버그 서명이라, 업데이트로 덮어쓰려면 같은 컴퓨터(같은 디버그 키)에서 빌드해야 합니다.
- 인터넷이 없으면 `www/index.html`의 안내 문구가 나옵니다.
