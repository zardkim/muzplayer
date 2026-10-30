<p align="center">
  <img src="frontend/public/logo.svg" width="96" alt="muzplayer 로고">
</p>

<h1 align="center">muzplayer</h1>

<p align="center">
  NAS에 있는 음악과 오디오북을 가족·지인이 각자 계정으로 듣는 개인용 웹 플레이어<br>
  Synology NAS · Docker · 휴대폰 앱처럼 설치(PWA) · 한국어 / English
</p>

---

## 소개

muzplayer는 NAS의 음악 폴더를 그대로 읽어 스트리밍 앱처럼 보여 줍니다. 파일을 옮기거나 변환하지 않고, 폴더는 읽기 전용으로만 씁니다.

- **음악:** 앨범·아티스트·곡·장르 목록, 검색, 내 플레이리스트, 최근 재생, 가사(`.lrc`·가사 태그, 시간 정보가 있으면 따라감)
- **좋아요·별점:** 곡과 앨범에 좋아요와 별 1~5개. 사람마다 따로 저장됨
- **믹스·스마트 재생목록:** 랜덤 100곡, 자주 듣는 곡, 가장 많이 들은 곡, 오랜만에 듣기, 별점 높은 곡, 아직 안 들은 곡, 최근 추가된 곡, 시대별 믹스.
  "★4 이상 + 발라드 + 30일 동안 안 들음"처럼 조건을 정하면 열 때마다 곡이 새로 정해지는 스마트 재생목록
- **영상:** 앨범·곡에 YouTube 뮤직비디오·라이브·커버곡을 검색해서 등록하고 앱 안에서 재생
- **차트·테마:** 멜론·벅스 주차별 차트 폴더와 "카페에서 듣기 좋은 노래" 같은 테마 모음 폴더를 배너 슬라이드와 추천 줄로 보여 줌.
  배너는 관리자가 AI(Gemini, OpenAI)로 만들고 말로 고칠 수 있음
- **오디오북:** 챕터·속도(0.75~2.5배)·±건너뛰기·취침 타이머, 사용자별 이어 듣기(기기를 바꿔도 이어짐),
  Audiobookshelf에서 책 정보·듣던 위치 가져오기
- **여러 사용자:** 계정마다 좋아요·별점·플레이리스트·재생 기록·듣던 위치가 따로 저장됨. 관리자 화면에서 계정·스캔 관리
- **휴대폰:** 홈 화면에 추가하면 앱처럼 실행, 잠금화면 재생 조작

## 스크린샷

<table>
  <tr>
    <td align="center"><img src="docs/screenshots/home.jpg" width="240" alt="홈"><br>홈</td>
    <td align="center"><img src="docs/screenshots/charts.jpg" width="240" alt="차트·테마"><br>차트·테마</td>
    <td align="center"><img src="docs/screenshots/theme.jpg" width="240" alt="테마 모음"><br>테마 모음</td>
  </tr>
  <tr>
    <td align="center"><img src="docs/screenshots/player.jpg" width="240" alt="재생 화면"><br>재생 화면</td>
    <td align="center"><img src="docs/screenshots/books.jpg" width="240" alt="오디오북"><br>오디오북</td>
    <td align="center"><img src="docs/screenshots/bookplayer.jpg" width="240" alt="오디오북 재생"><br>오디오북 재생</td>
  </tr>
</table>

<img src="docs/screenshots/desktop-charts.jpg" alt="PC 화면 — 차트·테마">

> 스크린샷의 가수·곡·책 이름과 커버는 모두 데모용으로 만든 것입니다.

## 설치 (Synology NAS)

빌드는 필요 없습니다. 이미지를 받고 `.env`만 채우면 됩니다. 컨테이너는 `app`과 `db`(PostgreSQL) 두 개입니다.

### 1. 폴더 준비

NAS에 `muzplayer` 폴더를 만들고 이 저장소의 두 파일만 복사합니다. 나머지 폴더는 처음 실행할 때 자동으로 생깁니다.

```
/volume1/docker/muzplayer/
├── docker-compose.yml   ← deploy/docker-compose.yml (수정하지 않음)
├── .env                 ← deploy/.env.example 을 복사해서 값 입력
├── app/                 ← 커버 캐시 등 앱 데이터 (자동 생성)
├── db/                  ← 데이터베이스 (자동 생성)
├── conf/                ← 앱에서 바꾼 설정 저장(API 키 등) (자동 생성)
└── library/             ← 자동 생성. 읽기 전용으로 연결
    ├── music/           ← 음악 폴더를 여기에 마운트
    └── audiobook/       ← 오디오북 폴더를 여기에 마운트 (없거나 비어 있으면 오디오북 메뉴가 숨겨짐)
```

- `library/music`·`library/audiobook`은 직접 연결합니다(아래). 연결 전에도 앱은 정상 시작하고, 스캔하면 "음악 폴더를 찾지 못했습니다"로 끝납니다.
- 앱은 `library/`에 아무것도 쓰지 않습니다.

**음악·오디오북 연결하기**

기존 공유 폴더를 `library/music`, `library/audiobook`에 bind 마운트합니다. Synology 작업 스케줄러 → **트리거된 작업 → 부트업**(root)에 등록하면 재부팅 뒤에도 유지됩니다.

```bash
mkdir -p /volume1/docker/muzplayer/library/music /volume1/docker/muzplayer/library/audiobook
mount --bind /volume1/music     /volume1/docker/muzplayer/library/music
mount --bind /volume1/audiobook /volume1/docker/muzplayer/library/audiobook
# 부팅 때 컨테이너가 마운트보다 먼저 떴을 수 있으므로 다시 시작
docker compose -f /volume1/docker/muzplayer/docker-compose.yml restart app
```

- 다른 NAS·PC의 공유(NFS·SMB)를 같은 자리에 마운트해도 됩니다.
- **심볼릭 링크로는 안 됩니다.** `library/music`을 `/volume1/music`을 가리키는 링크로 만들거나, 라이브러리 안의 링크가 `library/` 밖의 절대 경로를 가리키면
  컨테이너 안에서 찾을 수 없습니다. 링크 대신 마운트를 쓰세요.
- 앱을 띄운 뒤에 마운트하면 앱을 다시 시작해야 보입니다(`MUSIC_MOUNT_PROPAGATION=rslave`면 바로 보임, `.env.example` 참고).

### 2. 레지스트리 로그인 (처음 한 번)

```bash
echo '<시크릿>' | docker login harbor.nurilab.pe.kr -u 'robot$muzplayer+deploy' --password-stdin
```

### 3. `.env` 설정

| 항목 | 설명 |
|---|---|
| `MUZPLAYER_VERSION` | 실행할 버전. 기본값 `latest`(항상 최신 빌드). 특정 버전에 고정하려면 `0.8.0`처럼 적음 |
| `HTTP_PORT` | NAS에서 열 포트(기본 `18150`). 역방향 프록시는 `http://<NAS>:<HTTP_PORT>`로 연결 |
| `PUID` / `PGID` | 앱이 실행될 사용자(`id <사용자>`로 확인). `library/`를 읽을 수 있어야 함 |
| `POSTGRES_PASSWORD` | 긴 임의 문자열. 처음 실행한 뒤에는 바꾸지 않음 |
| `SCAN_INTERVAL_MINUTES` | 자동 재스캔 주기(기본 60분, `0`이면 수동만) |
| `COOKIE_SECURE` | HTTPS 뒤에서는 `true`. IP로 직접 테스트할 때만 `false` |

관리자 계정과 AI·YouTube API 키는 `.env`가 아니라 앱 안에서 정합니다(아래 4번).

### 4. 실행과 처음 설정

```bash
cd /volume1/docker/muzplayer
docker compose up -d
```

1. 브라우저로 열면 **관리자 계정 만들기** 화면이 나옵니다. **여기서 처음 만든 계정이 관리자**가 되고, 그 뒤로는 이 화면이 닫힙니다.
   - 먼저 접속한 사람이 관리자가 되므로, 역방향 프록시로 외부에 열기 전에 `http://<NAS>:18150`에서 먼저 만드세요.
2. 관리자 화면 → **라이브러리 폴더**에서 음악 폴더 바로 아래 폴더마다 종류를 고릅니다(아래 "폴더 구조").
3. **스캔 시작**을 누릅니다.
4. 관리자 화면 → **사용자**에서 가족·지인 계정을 만듭니다.
5. (선택) 관리자 화면 → **외부 서비스 키**에 AI 배너(Gemini·OpenAI)와 YouTube 검색 API 키를 넣습니다. 저장하면 다시 시작하지 않아도 바로 쓰입니다.

### 5. 휴대폰에서 앱처럼 쓰기

- **iPhone:** Safari → 공유 → **홈 화면에 추가**
- **Android:** Chrome → 설정 화면의 **앱으로 설치**

### 업데이트

1. DB를 백업합니다(아래 "백업·복구"의 백업 명령).
2. 새 이미지를 받아 실행합니다. `MUZPLAYER_VERSION`이 `latest`(기본값)면 `.env`는 그대로 두고, 특정 버전에 고정했다면 그 값을 바꿉니다.
   ```bash
   docker compose pull && docker compose up -d
   docker compose logs --tail 30 app      # "migrating database schema 0003 -> 0004" / "up to date"
   ```

- **DB 변경(마이그레이션)은 앱이 시작할 때 자동으로 합니다.**
  - 여러 버전을 건너뛰어도 차례대로 한 번에 올립니다.
  - 중간에 실패하면 **DB는 업데이트 전 그대로** 남습니다. 로그에 `migration failed`와 원인이 나오고, 이전 버전으로 되돌리면 그대로 쓸 수 있습니다.
- **이미 업데이트된 DB에 이전 버전 이미지를 올리면** DB를 건드리지 않고 시작을 멈춥니다(`database ... is newer than this image`).
  - 새 버전으로 다시 올리거나, 업데이트 전에 만든 백업으로 복구한 뒤 이전 버전을 씁니다.

| 버전 | 해야 할 일 |
|---|---|
| 0.1 → 0.2 | 새 `docker-compose.yml`로 교체, `.env`에 `MUSIC_ROOT` 추가(보통 `MUSIC_PATH`와 같은 값) |
| 0.2 → 0.3 | 라이브러리 폴더에서 차트·컴필레이션 폴더 종류를 고르고 스캔(DB 백업 권장) |
| 0.3 → 0.4 | 새 `docker-compose.yml`로 교체. 오디오북을 쓰려면 `.env`에 `AUDIOBOOK_PATH` 추가(DB 백업 권장) |
| 0.4 → 0.5 | 새 `docker-compose.yml`로 교체. 테마 폴더를 라이브러리 폴더에서 `테마`로 지정하고 스캔. AI 배너를 쓰려면 `GEMINI_API_KEY` 추가(선택) |
| 0.5.0 → 0.5.1 | 새 `docker-compose.yml`로 교체(경로를 잘못 적으면 시작하지 않도록 바뀜) |
| 0.5 → 0.7 | 새 `docker-compose.yml`로 교체(`YOUTUBE_API_KEY` 추가, 선택). 업데이트 뒤 첫 스캔에서 앨범 커버를 한 번 다시 만들어서 평소보다 오래 걸림. "즐겨찾기"는 "좋아요"로 이름이 바뀜(데이터 그대로) |
| 0.7 → 0.8 | **`docker-compose.yml` 교체 필수.** 예전 파일로 받으면 시작은 되지만 `conf/`가 연결되지 않아 앱에서 넣은 키가 컨테이너를 다시 만들 때 사라짐. 폴더 구조와 `.env`도 바뀜. 아래 "0.8로 옮기기" 참고 |

**0.8로 옮기기** (곡·좋아요·별점·재생목록·재생 기록은 그대로 남습니다. 파일 경로를 음악 폴더 기준으로 저장하기 때문입니다.)

먼저 라이브러리 안에 심볼릭 링크가 있는지 확인하세요. 0.8부터는 `library/` 밖을 가리키는 링크를 따라가지 못하므로, 나오는 링크는 마운트로 바꿔야 합니다.

```bash
find /volume1/music -type l | head
```

```bash
cd /volume1/docker/muzplayer
docker compose down
sudo mv data/app app && sudo mv data/postgres db && sudo rmdir data     # db는 sudo가 꼭 필요
sudo mkdir -p library/music library/audiobook
# 음악·오디오북을 library/music, library/audiobook에 마운트 (위 "음악·오디오북 연결하기")
```

1. `docker-compose.yml`을 새 파일로 바꿉니다.
2. `.env`는 새 `deploy/.env.example`을 보고 다시 씁니다. `POSTGRES_PASSWORD`·`PUID`·`PGID`는 **기존 값 그대로** 두고,
   `MUSIC_PATH`·`MUSIC_ROOT`·`AUDIOBOOK_PATH`·`DATA_PATH`·`ADMIN_*`·`*_API_KEY`·`AI_PROVIDER`·`*_IMAGE_MODEL` 줄은 지웁니다.
3. 포트 기본값이 `18150`으로 바뀌었습니다. 예전 포트를 계속 쓰려면 `HTTP_PORT`를 그대로 두고, 바꾸면 역방향 프록시 주소도 바꿉니다.
4. `docker compose pull && docker compose up -d` 후 관리자 화면 → **외부 서비스 키**에 API 키를 다시 넣습니다.

### 스캔 중 문제가 생기면

| 상황 | 처리 |
|---|---|
| 파일 하나를 읽지 못함(깨진 파일, 권한) | 그 파일만 오류로 세고 계속 진행. 관리자 화면 "오류 상세"에서 확인 |
| 폴더를 읽지 못함(권한, 꺼진 공유 폴더) | 그 폴더 아래 곡은 "없어짐"으로 처리하지 않음 |
| 음악 폴더 전체가 비어 보임(마운트 해제) | 스캔을 실패로 끝내고 아무것도 숨기지 않음 |
| 관리자가 **스캔 중지**를 누름 | 지금 파일까지 저장하고 멈춤. "없어짐" 처리와 정리는 하지 않음 |
| 스캔 중 앱·NAS가 재시작됨 | 다음 시작 때 "중단됨"으로 표시. 그때까지 읽은 곡은 남고 "없어짐" 처리는 하지 않음 |

중지·중단된 뒤에는 **스캔 시작**을 다시 누르면 됩니다. 이미 읽은 파일은 건너뛰므로 남은 부분만 처리합니다.

### 큰 라이브러리

- **첫 스캔**은 모든 파일의 태그와 커버를 읽으므로 곡 수에 비례해 오래 걸립니다. 그 뒤의 스캔은 바뀐 파일만 읽습니다.
  관리자 화면의 마지막 스캔 옆에 걸린 시간이 나옵니다. 자동 스캔 주기(`SCAN_INTERVAL_MINUTES`)는 이 시간보다 넉넉하게 둡니다.
- **앨범 커버**는 스캔할 때 300px·1000px로 줄여 저장해 둡니다. `cover.jpg`를 바꾸거나 파일에 넣은 커버를 바꾸면 다음 스캔에서 다시 만듭니다.
  휴대폰·브라우저는 한 번 받은 커버를 다시 받지 않습니다(커버가 바뀌면 주소가 바뀜).
- 커버가 이상하면 관리자 화면 → **커버 다시 만들기**로 전부 다시 만듭니다.

## 폴더 구조

앨범·아티스트는 파일 태그로 묶습니다. 폴더에서 읽는 것은 **음악 폴더 바로 아래 폴더의 종류**와 **`비정규` 폴더 여부**뿐입니다.

```
library/music/                              ← 음악 폴더
├── album/                                  ← 종류: 앨범 (기본값)
│   └── 아티스트/[2017] 앨범명/01 곡.flac
│       └── 비정규/[2019] 라이브/            ← 비정규 앨범으로 표시 (`비정규` 또는 `Unofficial`)
├── chart music/                            ← 종류: 차트
│   └── 멜론/2026-10-4주/001 가수 - 제목.mp3  ← 폴더 하나 = 차트 하나, 바로 아래 폴더 = 출처
├── theme music/                            ← 종류: 테마
│   ├── 팝송/한국인이 좋아하는 팝송 TOP100/   ← 폴더 하나 = 테마 하나, 중간 폴더 = 분류
│   ├── 카페에서 듣기 좋은 노래/banner.jpg    ← banner.jpg가 있으면 배너로 사용
│   └── 2020년 걸그룹 노래 모음/CD1, CD2/     ← CD 폴더는 한 모음으로 합침
```

**종류**

| 종류 | 처리 |
|---|---|
| 앨범 | 아티스트/앨범으로 묶음 |
| 컴필레이션 | 앨범 아티스트 태그가 없으면 Various Artists로 묶음 |
| 차트 | 앨범 목록에 넣지 않고 차트로 보여 줌 |
| 테마 | 앨범 목록에 넣지 않고 테마 모음으로 보여 줌 |
| 제외 | 스캔하지 않음 |

종류는 관리자 화면 **라이브러리 폴더**에서 고르고, 다음 스캔부터 반영됩니다.

**차트·테마**

- 곡 순서는 파일명 앞 번호(`001 …`) → 트랙 번호 태그 → 파일명 순서입니다.
- 차트·테마 곡도 곡 목록과 검색에는 나옵니다. 같은 곡이 여러 곳에 있으면 최신 차트 주차의 파일 하나만 보입니다.

**파일 이름과 가사**

- 파일·폴더 이름에는 `: ? * " < > |`와 끝의 마침표를 쓰지 않습니다(SMB 호환).
- 가사는 곡과 같은 이름의 `.lrc`(UTF-8·CP949) 또는 파일의 가사 태그에서 읽습니다.

**링크와 마운트**

- 링크된 폴더도 따라가 스캔합니다.
- 끊긴 링크나 꺼진 공유 폴더 아래 곡은 "없어짐"으로 처리하지 않습니다.
- 음악 폴더 전체가 비어 보이면 스캔을 멈춥니다.

### 재생 형식

변환 없이 원본을 그대로 보냅니다.

| 형식 | 재생되는 곳 |
|---|---|
| MP3 · AAC(m4a) · FLAC · WAV | 어디서나 |
| ALAC · AIFF | iPhone Safari |
| OGG / Opus | Chrome · Android (iPhone은 버전에 따라 다름) |
| WMA · APE | 브라우저가 재생하지 못해 건너뜀 |

## 차트·테마 배너

탐색 → **차트·테마** 맨 위에는 배너 슬라이드가 있습니다. 출처별 최신 차트와 오늘의 테마가 나오고, 홈 맨 위에도 같은 슬라이드가 보입니다.

배너는 아래 순서에서 먼저 있는 것을 씁니다. 제목 글자는 이미지에 그리지 않고 화면에서 위에 얹습니다.

1. 그 모음에 만든 AI 배너
2. 차트 출처 전체 배너(예: 멜론의 모든 주차가 함께 씀)
3. 모음 폴더의 `banner.jpg`(·`.png`·`.webp`)
4. 상위 곡 커버로 자동으로 그린 배너

**AI 배너 만들기**

- 관리자 화면 → **외부 서비스 키**에 Gemini API 키를 넣으면 관리자에게 차트·테마 상세 화면의 **AI 배너** 버튼이 보입니다.
- OpenAI를 쓰려면 같은 곳에서 AI 서비스를 OpenAI로 바꾸고 키를 넣습니다. 이미지 모델은 비워 두면 기본값을 씁니다.
- 앱이 채워 준 프롬프트로 만든 뒤, "더 따뜻한 색으로"처럼 말로 고치고 적용합니다.
- 만들기·고치기 한 번마다 유료 이미지 요청이 한 번 나갑니다(Gemini 2K 기준 약 $0.05).
- 키는 서버의 `conf/settings.json`(앱 사용자만 읽을 수 있음)에만 저장되고, 화면에 다시 보이지 않으며 DB·로그에 남지 않습니다.
- 오류가 나면 `docker compose logs app | grep "ai banner"`에서 이유를 볼 수 있습니다.

## 믹스·스마트 재생목록

- **믹스:** "내 음악"과 홈의 "나를 위한 믹스". 들은 기록·별점·태그로 고르는 규칙이고, 사람마다 다릅니다.
  - 무작위 믹스는 열 때마다 새로 고르고, **다시 섞기**로 바꿀 수 있습니다. 재생 중에는 순서가 바뀌지 않습니다.
  - 곡이 없는 믹스(예: 아직 별점을 준 곡이 없음)는 보이지 않습니다.
- **재생 횟수:** 30초 또는 곡의 절반을 들으면 한 번으로 셉니다.
- **스마트 재생목록:** 플레이리스트 화면 → **스마트 재생목록 만들기**. 장르·아티스트·연도·별점·좋아요·재생 횟수·마지막으로 들은 날·추가된 날·폴더 종류·곡 길이로 조건을 정합니다.
  곡을 직접 넣거나 빼지 않고, 지금 곡을 고정하려면 **플레이리스트로 저장**을 누릅니다.

## 영상 (YouTube)

앨범 화면의 **영상** 버튼, 곡 메뉴의 **영상 보기**, 재생 화면의 영상 버튼에서 열립니다.

1. 종류(뮤직비디오·라이브·커버·기타)를 고르고 검색합니다. 검색어는 아티스트·제목으로 미리 채워집니다.
2. 목록에서 **등록**을 누르면 모든 사용자에게 보입니다. 지우기는 등록한 사람과 관리자만 할 수 있습니다.

- **검색 키:** 관리자 화면 → **외부 서비스 키**에 YouTube API 키를 넣어야 앱 안에서 검색됩니다.
  - Google Cloud 콘솔에서 **YouTube Data API v3**를 켜고 API 키를 만듭니다. 무료 한도로 하루 약 100번 검색할 수 있습니다.
  - 키 제한은 **API 제한: YouTube Data API v3만**, **애플리케이션 제한: 없음 또는 NAS의 IP 주소**로 둡니다. "HTTP 리퍼러(웹사이트)" 제한을 걸면 서버에서 부르는 검색이 거부됩니다.
  - 키가 없으면 YouTube에서 찾은 영상의 주소를 붙여 넣어 등록합니다.
- 영상은 YouTube 공식 플레이어로 재생하며, 시작하면 음악은 일시정지합니다. 음악 대기열에는 들어가지 않습니다(YouTube 약관, iPhone은 화면이 꺼지면 영상이 멈춤).
- 일부 뮤직비디오는 다른 사이트에서 재생할 수 없게 되어 있습니다. 그때는 **YouTube에서 보기** 링크가 나옵니다.
- 역방향 프록시에서 CSP를 쓰면 `frame-src https://www.youtube-nocookie.com`, `img-src https://i.ytimg.com`, `script-src https://www.youtube.com`을 허용해야 합니다.

## 오디오북

`library/audiobook` 폴더를 직접 읽어 재생합니다. Audiobookshelf 없이도 동작하고, 책을 묶는 규칙은 Audiobookshelf와 같습니다.

```
audiobook/
├── 저자/시리즈/1권 제목/book.m4b, cover.jpg   ← 저자/시리즈/책
├── 저자/책 제목/CD1/01.mp3, CD2/01.mp3        ← CD·Disc 폴더는 같은 책
└── 낱권.m4b                                    ← 맨 위의 파일 하나 = 책 하나
```

- **책 정보:** 첫 파일의 태그에서 읽습니다(앨범=제목, 아티스트=저자, 작곡가=내레이터). 태그가 없으면 폴더 이름을 씁니다.
- **챕터:** `.m4b`·mp3 안의 챕터를 씁니다. 없으면 파일마다 챕터 하나입니다.
- **커버:** 폴더의 이미지를 먼저 쓰고, 없으면 파일 안의 커버를 씁니다.
- **듣던 위치:** 사용자별로 서버에 저장되어 다른 기기에서 이어 듣습니다.

**Audiobookshelf에서 옮기기**

1. Audiobookshelf와 같은 폴더를 `library/audiobook`에 마운트하고 스캔합니다.
2. 관리자 화면 → 오디오북 → **Audiobookshelf에서 가져오기**에 주소와 관리자 API 키(Audiobookshelf 설정 → API Keys)를 넣습니다.
3. 편집한 책 정보·챕터·커버와 사용자별 듣던 위치를 한 번 가져옵니다. 키는 저장하지 않습니다.
4. 가져온 정보는 다시 스캔해도 태그로 덮어쓰지 않습니다. 이후에는 Audiobookshelf를 꺼도 됩니다.

## 백업·복구

DB에는 계정·플레이리스트·좋아요·별점·재생 기록·등록한 영상·듣던 위치가 들어 있습니다. API 키는 `conf/`에 있으니 함께 보관하세요. 커버 캐시는 다시 스캔하면 새로 만들어집니다.

Synology 작업 스케줄러(매일, root)에 등록합니다.

```bash
cd /volume1/docker/muzplayer && mkdir -p backup && \
docker compose exec -T db pg_dump -U muzplayer -Fc muzplayer > backup/muzplayer-$(date +%F).dump && \
find backup -name 'muzplayer-*.dump' -mtime +14 -delete
```

복구:

```bash
docker compose stop app
docker compose exec -T db pg_restore -U muzplayer -d muzplayer --clean --if-exists < backup/muzplayer-YYYY-MM-DD.dump
docker compose start app
```

## 개발

개발 환경, 구조, 빌드·릴리스, 테스트는 [위키](https://gitea.nurilab.pe.kr/nuricom/muzplayer/wiki)에 있습니다. 기능 계획과 변경 이력은
[music_player_plan.md](music_player_plan.md), 화면 디자인 기준은 [docs/design.md](docs/design.md)에 있습니다.
