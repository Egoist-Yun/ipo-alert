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

## 푸시 알림 설정 (FCM)
수집기가 보내는 알림은 FCM 푸시(앱 이름 "공모주 달력"으로 도착)가 먼저이고, FCM이 실패할 때만 ntfy로 갑니다.
1. Firebase 콘솔에서 프로젝트를 만들고 안드로이드 앱(패키지 `io.github.egoistyun.ipoalert`)을 추가한 뒤 `google-services.json`을 내려받습니다.
2. 그 파일을 `app/android/app/google-services.json`(빌드용 복사본이면 `C:\ipo-app-buildndroidpp\`)에 둡니다.
   이 파일은 `.gitignore`에 들어 있어 커밋되지 않습니다. 공개 저장소이므로 절대 올리지 마세요. 없으면 푸시 플러그인은 켜지지 않고 앱은 그대로 동작합니다.
3. Firebase 프로젝트 설정 > 서비스 계정에서 새 비공개 키(JSON)를 만듭니다.
4. GitHub 저장소 Settings > Secrets and variables > Actions에 비밀값 2개를 만듭니다.
   - `FCM_SERVICE_ACCOUNT`: 3번 JSON 파일의 내용 전체(텍스트 그대로)
   - `FCM_TOKEN`: 앱 설치 뒤 아래 방법으로 복사한 기기 토큰
5. APK를 새로 빌드해서 설치합니다. 푸시 플러그인이 들어간 APK부터 앱 알림이 동작합니다.
6. 앱의 실전 성적 화면 > "앱 알림"에서 "토큰 복사"를 눌러 `FCM_TOKEN`에 붙여 넣습니다.
7. Actions 탭에서 `test-push`를 실행하면 "공모주 테스트 알림"이 도착합니다.

**토큰 갱신:** 앱을 지웠다 다시 설치하거나 데이터를 지우면 토큰이 바뀝니다. 앱이 "토큰이 바뀌었어요" 안내를 띄우거나 ntfy로
"앱 알림 토큰이 무효예요"가 오면, 6번처럼 새 토큰을 복사해 `FCM_TOKEN` 비밀값만 바꿉니다.
값(토큰, 서비스 계정, ntfy 토픽)은 이 문서나 저장소에 적지 않습니다.

## 증권사 목록을 바꿀 때
`web/brokers.js`의 `BROKER_APPS`와 `android/app/src/main/AndroidManifest.xml`의 `<queries>`를 같이 고쳐야 합니다
(안드로이드 11 이상은 매니페스트에 적힌 패키지만 찾을 수 있습니다).

## 알아둘 점
- 화면(목록/상세/실전 성적)은 웹 주소의 해시로 전환됩니다. 폰의 뒤로가기 키가 상세에서 목록으로 가도록 `MainActivity.java`가 웹 기록 뒤로가기를 처리합니다(이 파일을 바꾸면 APK를 다시 빌드해야 합니다).
- 디버그 서명이라, 업데이트로 덮어쓰려면 같은 컴퓨터(같은 디버그 키)에서 빌드해야 합니다.
- 인터넷이 없으면 `www/index.html`의 안내 문구가 나옵니다.
