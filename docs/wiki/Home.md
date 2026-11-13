# muzplayer 위키

NAS에 있는 음악·오디오북·뮤직 영상을 가족·지인이 각자 계정으로 듣는 셀프호스팅 웹 플레이어입니다.
휴대폰에서는 앱처럼 설치(PWA)해서 쓰고, PC에서는 브라우저나 Windows 앱으로 씁니다.

## 시작하기

1. [[설치]] — Docker Compose(Synology NAS·Portainer 포함)로 설치하고 처음 설정
2. [[라이브러리]] — 음악 폴더 구조, 폴더 종류(앨범·차트·테마·추출 음원), 태그 규칙, 스캔
3. [[기능]] — 플레이어, 가사, 차트·테마, 라디오, 뮤직 영상·음원 추출, 오디오북, 스마트 재생목록
4. [[업데이트]] — 새 버전으로 올리기, 버전별로 할 일
5. [[백업과 복구|백업과-복구]]
6. [[Windows 앱|Windows-앱]]
7. [[외부 서비스와 라이선스|외부-서비스와-라이선스]]
8. [[개발]] — 직접 빌드, 로컬 개발, 테스트

## 한눈에

| | |
|---|---|
| 이미지 | [`zardkim/muzplayer`](https://hub.docker.com/r/zardkim/muzplayer) (linux/amd64, linux/arm64) |
| 컨테이너 | `app`(FastAPI + Vue 웹 앱) + `db`(PostgreSQL 17) |
| 음악 폴더 | 읽기 전용으로 마운트. 앱은 `library/cover music`(추출 음원)에만 씀 |
| 언어 | 한국어 / English |
| 라이선스 | GPL-3.0-or-later |
