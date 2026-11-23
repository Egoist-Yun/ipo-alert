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
알림은 FCM **주제(topic) `ipo-alerts`** 로 갑니다. 앱을 설치하고 한 번 열면(`MainActivity`) 이 주제를 구독하므로,
**앱을 깐 사람은 모두 받습니다.** 기기 토큰을 복사하거나 재설치 때 바꿀 필요가 없습니다.
1. Firebase 콘솔에서 프로젝트를 만들고 안드로이드 앱(패키지 `io.github.egoistyun.ipoalert`)을 추가한 뒤 `google-services.json`을 내려받습니다.
2. 그 파일을 `app/android/app/google-services.json`(빌드용 복사본이면 `C:\ipo-app-build\android\app\`)에 둡니다.
   이 파일은 `.gitignore`에 들어 있어 커밋되지 않습니다. 공개 저장소이므로 절대 올리지 마세요.
   **이 파일 없이 빌드하면 알림 권한을 허용할 때 앱이 종료됩니다**(푸시 플러그인의 네이티브 예외라 막을 수 없음). 로컬 빌드는 이 파일을 반드시 둡니다.
3. Firebase 프로젝트 설정 > 서비스 계정에서 새 비공개 키(JSON)를 만듭니다.
4. GitHub 저장소 Settings > Secrets and variables > Actions에 비밀값을 만듭니다.
   - `FCM_SERVICE_ACCOUNT`: 3번 JSON 파일의 내용 전체(텍스트 그대로)
   - `GOOGLE_SERVICES_JSON`: 1번 `google-services.json`의 내용 전체. CI가 APK를 빌드할 때 필요하고, 없으면 빌드가 실패합니다.
5. APK를 새로 빌드해서 설치하고 앱을 한 번 엽니다. 알림 권한을 허용하면 실전 성적 화면의 "앱 알림"에 "공모주 알림을 받고 있어요"가 보입니다.
6. Actions 탭에서 `test-push`를 실행하면 제목 "공모주 달력", 본문 "테스트 알림이에요."인 알림이 도착합니다.

**한계:**
- 주제 발송은 구독자가 0명이어도 성공으로 응답합니다. 폰이 구독하지 않았으면(앱을 한 번도 열지 않았거나 푸시 플러그인이 없는 옛 APK) 알림이 사라지고, ntfy 예비 경로도 타지 않습니다.
- `NTFY_TOPIC` 없이 FCM만 쓰면 설정 오류를 폰으로 알려 줄 길이 없어 Actions 로그에만 남습니다.
- 주제 이름은 공개돼도 됩니다(발송에는 서비스 계정이 필요). 값(서비스 계정, ntfy 토픽)은 이 문서나 저장소에 적지 않습니다.

## 증권사 목록을 바꿀 때
`web/brokers.js`의 `BROKER_APPS`와 `android/app/src/main/AndroidManifest.xml`의 `<queries>`를 같이 고쳐야 합니다
(안드로이드 11 이상은 매니페스트에 적힌 패키지만 찾을 수 있습니다).

## 알아둘 점
- 화면(목록/상세/실전 성적)은 웹 주소의 해시로 전환됩니다. 폰의 뒤로가기 키가 상세에서 목록으로 가도록 `MainActivity.java`가 웹 기록 뒤로가기를 처리합니다(이 파일을 바꾸면 APK를 다시 빌드해야 합니다).
- 디버그 서명이라, 업데이트로 덮어쓰려면 같은 컴퓨터(같은 디버그 키)에서 빌드해야 합니다.
- 인터넷이 없으면 `www/index.html`의 안내 문구가 나옵니다.
