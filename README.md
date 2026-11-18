# 공모주 위험 신호 달력

청약 전에 공모주의 위험 신호를 모아 보여주고, 스마트폰으로 알려줍니다. 투자 권유가 아닌 공개 정보 정리입니다.

- 데이터: 38커뮤니케이션(청약 일정, 수요예측 결과, 신규상장, 종목 상세)
- 하루 2번(08:17, 17:47 KST 무렵, GitHub 사정으로 늦어질 수 있음)과 코드를 올릴 때마다 GitHub Actions가 수집해 `data/`에 저장하고 웹앱을 배포합니다.
- 설계: `docs/superpowers/specs/2026-11-17-ipo-risk-alert-design.md`
- 디자인 기준: `DESIGN.md`

## 처음 한 번 설정 (스마트폰)

1. 스마트폰에 **ntfy** 앱을 설치하고 `+`를 눌러 채널을 구독합니다. 채널 이름은 남이 추측하기 어려운 값(예: `ipo-` 뒤에 무작위 문자)으로 정하고, 같은 값을 GitHub 저장소의 Secret `NTFY_TOPIC`에 넣습니다.
2. 스마트폰 브라우저로 `https://<계정>.github.io/<저장소>/`를 열고 홈 화면에 추가합니다.
3. 알림을 누르면 해당 종목의 상세가 열립니다.

## GitHub 설정

1. 공개 저장소를 만들어 push합니다(무료 Pages는 공개 저장소에서만 동작).
2. Settings → Pages → Source를 **GitHub Actions**로 설정합니다.
3. Settings → Secrets and variables → Actions에 `NTFY_TOPIC`을 추가합니다.
4. Actions 탭에서 `update`를 한 번 수동 실행(Run workflow)합니다. 첫 실행에서는 청약이 끝나지 않은 종목들의 알림이 한꺼번에 올 수 있습니다.

## 개발

```bash
python -m pip install -r requirements.txt
python -m pytest -q
node --test web/calendar.test.js
python -m ipo.main            # NTFY_TOPIC 없이 실행하면 알림 없이 data/를 갱신합니다
python -m ipo.predict --report data/history.json
```

화면은 `web/`를 정적 서버로 열고(`python -m http.server -d web`) `web/ipos.json`(= `data/ipos.json` 복사본)을 읽습니다.
