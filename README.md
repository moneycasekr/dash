# 채널 현황 대시보드

1시간마다 유튜브 채널 숫자를 모아 `data/history.json`에 쌓고, `index.html`이 그걸 보여 줍니다.

## 설치 (한 번만)

1. **API 키 발급**: console.cloud.google.com → 새 프로젝트 → "YouTube Data API v3" 사용 설정 → 사용자 인증 정보 → API 키 만들기
2. **저장소 만들기**: GitHub에서 새 공개 저장소 `dash` 생성 → 이 폴더 파일 전부 업로드 (`.github` 폴더 포함)
3. **키 넣기**: 저장소 Settings → Secrets and variables → Actions → New repository secret
   - 이름 `YT_API_KEY`, 값 = 발급한 키
4. **페이지 켜기**: Settings → Pages → Source "Deploy from a branch", Branch `main` / `(root)` → Save
5. **첫 수집**: Actions 탭 → stats → Run workflow
6. 접속: `https://moneycasekr.github.io/dash/` → 휴대폰 공유 버튼 → "홈 화면에 추가"

## 채널 추가·변경

`channels.json`에 한 줄 추가 (`handle`은 @핸들, `color`는 점·그래프 색).

## 참고

- 유튜브 공개 수치라 구독자는 반올림되고 조회수는 몇 시간 늦게 반영될 수 있음
- 기록은 30일치만 보관
- 정각 실행은 GitHub 사정으로 몇 분~수십 분 늦을 수 있음
