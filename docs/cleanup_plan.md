# 전체 점검 결과와 수정 계획 (0.74.0 기준)

2026-11-18 점검.

## 진행 상황 (2026-11-18, 커밋 전)

| 단계 | 상태 |
|---|---|
| 1단계 | 완료. 6-1 사용자 전환 삭제 포함(사용자 결정). `ai_playlist.py`는 `ai_text.py`로 줄임(`ask_json`만 남김). 번역 키 49개 삭제(ko·en 1564 → 1515). `logs.action.switch`는 남김(180일 보관하는 활동 로그에 예전 기록이 있을 수 있음) |
| 2-1 | 완료. `backend/app/net.py`. 열쇠가 필요한 API 클라이언트(AI, YouTube, Audiobookshelf, GitHub 릴리스)는 오류 처리가 달라 그대로 둠 |
| 2-2 | 완료. `swipe.ts`의 `usePullToClose`, `SETTLE` |
| 2-3 | 완료. `style.css`의 `field`, `pill`, `pill-sm`, `pill-select` (33곳과 JS 상수 4곳) |
| 3-1, 3-2, 3-3 | 완료 |
| 3-4 | 하지 않음 (선택 항목. IP가 많은 공격자에게 시도 횟수를 더 주는 단점) |
| 3-5 | 조치 없음 (계획대로) |
| 4-1 | 완료. 영어만 지연 로딩. 한국어는 대체 언어라 기본 번들에 둠. i18n 청크 265KB → 206KB |
| 5-1, 5-2 | 완료. 마이그레이션 0040 |
| 6-2 | 하지 않음 (사용자 결정) |

검증 결과
- `vue-tsc`, 빌드, ruff F 통과
- 개발 서버 스모크 155/0. 사용자 전환 7건과 AI 1건을 빼고, 로그아웃 3건을 더했다.
- 브라우저 확인: 스마트 재생목록 창, 로그아웃, 당겨서 닫기(곡·오디오북), 언어 전환, 바뀐 클래스의 픽셀 비교

남은 발견 (이번 범위 밖)
- `alembic check`에 이전부터 있던 차이가 있다: `extract_jobs.created_at`과 `merge_not_same.created_at`의 nullable 표시, 마이그레이션에만 있는 부분 유니크 인덱스 2개(`uq_playlists_default`, `uq_video_playlists_default`). 동작에는 영향이 없다.

## 0. 요약

| 영역 | 상태 | 할 일 |
|---|---|---|
| 백엔드 품질 (ruff, vulture) | 양호. 실제 문제는 몇 건뿐 | 안 쓰는 import 3건, `raise ... from` 8건 |
| 의존성 취약점 | pip-audit 0건. npm은 개발 도구에만 해당 | 없음. 버전 올릴 때 함께 해결 |
| 죽은 코드 | UI는 없어졌는데 백엔드가 남은 기능 2개, 안 쓰는 컴포넌트 1개 | 정리 (1개는 사용자 확인 필요) |
| 중복 코드 | 전반적으로 적음 | HTTP 헬퍼 약 8벌, 당겨서 닫기 제스처 3벌, 입력·버튼 클래스 반복 |
| 보안 | 인증, 경로 처리, 쿠키, 잠금 모두 양호 | 프록시 신뢰 범위, 보안 헤더, 벅스 키 |
| 성능 | 쿼리 루프 문제 없음 | i18n 청크 268KB를 줄이기 |
| DB | 구조 양호 | FK 인덱스 4개 (낮은 우선순위) |

검증 기준은 단계마다 같다.
- `vue-tsc --noEmit`
- `npm run build`
- 개발 서버 스모크: `scripts/smoke_test.sh`, 현재 160/0
- 릴리스 이미지 스모크: 두 DB에서 160/0, 155/0
- 라우트를 지우면 스모크 체크 수가 줄어든다. 줄어든 수를 그 단계의 새 기준으로 적는다.

---

## 1단계 — 죽은 코드 정리 (위험 낮음)

| # | 대상 | 근거 | 조치 |
|---|---|---|---|
| 1-1 | `frontend/src/components/PlayerControls.vue` (52줄) | 아무 곳에서도 import하지 않는다. 0.2.0 이후 그대로 남아 있다. | 파일 삭제 |
| 1-2 | `POST /playlists/ai` (`backend/app/api/me.py:234`) | 0.69.1에서 "AI로 만들기" UI를 없앴다. 지금은 스모크 테스트만 이 라우트를 부른다. | 아래 참고 |
| 1-3 | 안 쓰는 import: `album_notes.py:34`, `api/library.py:17`, `artist_aliases.py:27` | ruff F401 | 삭제 |
| 1-4 | `artist_images.py:237` `SITES`, `transcode.py:36` `QUALITIES` | 어디서도 참조하지 않는다. 프론트엔드의 `QUALITIES`는 `stream.ts`에 따로 있다. | 삭제 |
| 1-5 | `api.ts:44` `streamUrl`, `audioGraph.ts:182` `tailSrc` | export했지만 쓰는 곳이 없다. `public/*.js`와 `native.ts`에서도 쓰지 않는다. | 삭제 |
| 1-6 | 번역 키 약 40개 후보 | 정적 검색으로 후보를 뽑았다. 확실한 것: `ai.*` 전체, `common.playAll`, `videos.upNext`, `notes.heading`, `search.hint`, `home.random100`, `admin.folderCol` | 키마다 동적 사용(`` `${x}.title` `` 같은 형태)을 확인한 뒤, ko와 en에서 함께 삭제 |

**1-2 세부 사항**
- 지울 것:
  - 라우트와 그 안의 재생목록 생성 로직
  - `appConfig.aiPlaylists` (`config.ts`, `main.ts:44`, `IntegrationsCard.vue:66`)
  - `/config`의 `ai_playlists` 응답 필드
  - `ai.*` 번역 키
- 남길 것: `ai_playlist.py` 모듈. `ask_json`은 `extract.py:689`의 태그 추측에 쓰이고, `configured()`도 쓰인다. 모듈 이름을 `ai_text.py` 같은 이름으로 바꾸는 것은 선택 사항이다.
- 함께 고칠 것: `scripts/smoke_test.sh`의 해당 체크를 지우고 새 기준 수를 적는다.

## 2단계 — 중복을 공용으로 (위험 낮음~중간)

### 2-1. 백엔드 HTTP 헬퍼 통합 → `backend/app/http.py`

같은 브라우저 UA 문자열과, 비슷한 `urlopen` 래퍼가 여러 모듈에 따로 있다.

| 파일 | 지금 있는 것 |
|---|---|
| `radio.py:46,89` | `UA`, `_open` |
| `radio_now.py:25,39` | `UA`, `_json` |
| `album_notes.py:47,113` | `_UA`, `_get` (BeautifulSoup 반환) |
| `lyrics_fetch.py:34,57` | `_UA`, `_get` |
| `artist_images.py:40,137,236,245` | `USER_AGENT`, `_get`, `BROWSER_UA`, `_page` |
| `artist_aliases.py:42,53` | `USER_AGENT`, `_json` |
| `extract.py:59,789` | `UA`, `_fetch_cover` 외 |
| `youtube.py:44` | `_get` |

`artist_images.py:40`의 UA에는 버전이 `muzplayer/0.9`로 하드코딩되어 있다. 다른 곳은 `settings.version`을 쓴다.

새 모듈의 내용:
- 상수: `BROWSER_UA`, `APP_UA` (`settings.version` 사용)
- 함수: `get(url, *, headers, data, timeout) -> bytes`, `get_json(...)`, `get_page(url, referer) -> BeautifulSoup`

각 모듈의 오류 변환은 그대로 둔다. 예를 들어 `bugs_artists`는 `Unreachable`로, `artist_images`는 `ImageError`로 바꾼다. 바꾸는 것은 요청을 보내는 부분뿐이다.

검증: 스모크 테스트, 그리고 관리자 화면의 앨범 소개 찾기, 가사 찾기, 아티스트 사진 찾기, 라디오 재생을 직접 확인한다.

### 2-2. 당겨서 닫기 제스처 → `usePullToClose` 컴포저블

다음 세 파일에 같은 코드가 들어 있다: `dragY`, `settling`, `settle()`, `useSwipe({axes:['y']...})`, 닫는 기준 `dy > 140 || (fast && dy > 40)`.
- `NowPlaying.vue:65-85`
- `LivePlayer.vue:41-60`
- `BookPlayer.vue:56-75`

계획:
- `swipe.ts` 옆에 `usePullToClose(scroller, close)`를 만든다. `{ dragY, settling, pull, settle }`을 돌려준다.
- 좌우로 넘기는 제스처(로고, 커버)는 화면마다 달라서 각 파일에 그대로 둔다.
- `settling` transition 클래스 문자열도 5번 반복된다. 이것도 컴포저블이 돌려주게 한다.

검증: 휴대폰 폭에서 세 플레이어를 각각 당겨서 닫아 본다 (Playwright 또는 실기기).

### 2-3. 자주 반복되는 UI 클래스 (작게만)

디자인 시스템을 새로 만들지는 않는다. 가장 많이 반복되는 두 가지만 `style.css`에 Tailwind `@utility`로 묶는다.

| 클래스 문자열 | 반복 | 제안 |
|---|---|---|
| `h-12 rounded-full bg-surface px-4 text-base text-ink outline-none focus:ring-2 focus:ring-ink` (높이 52px 변형 4회 포함) | 10 | `field` |
| `h-8 / h-10 rounded-full border border-line-strong px-3·4 text-[13px]·[14px] hover:border-ink` | 15 | `pill-btn`, `pill-btn-sm` |
| `h-10 rounded-full border border-line-strong bg-bg px-3 text-sm` (`<select>`, 대부분 `AdminView`) | 7 | `pill-select` |

검증: 바꾸기 전후 스크린샷을 비교한다 (관리자, 설정, 재생목록 화면).

## 3단계 — 보안 보강

| # | 항목 | 내용 | 조치 |
|---|---|---|---|
| 3-1 | 프록시 신뢰 범위 | `backend/entrypoint.sh`가 uvicorn을 `--forwarded-allow-ips='*'`로 실행한다. 컨테이너 포트가 프록시를 거치지 않고 열려 있으면 누구나 `X-Forwarded-For`를 위조할 수 있다. 그러면 가입 횟수 제한(`api/auth.py:270`, `request.client.host` 기준)을 우회할 수 있고, 활동 로그의 IP도 오염된다. | `FORWARDED_ALLOW_IPS` 환경변수를 추가한다. 기본값은 사설 대역(`127.0.0.1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16`)으로 한다. README와 `.env` 예시에 적는다. |
| 3-2 | 보안 응답 헤더 없음 | `main.py`에 `X-Content-Type-Options`, `X-Frame-Options`(또는 CSP `frame-ancestors`), `Referrer-Policy` 헤더가 없다. | 작은 미들웨어 하나로 붙인다. CSP 전체 적용은 YouTube iframe, 크롬캐스트, 인라인 스타일 때문에 깨질 위험이 크다. 이번에는 하지 않는다. |
| 3-3 | 벅스 가사 API 키 | `lyrics_fetch.py:141`에 키가 하드코딩되어 있고 `http://`로 보낸다. | 같은 엔드포인트가 https를 지원하는지 확인한다. 지원하면 https로 바꾼다. 키는 공개 앱 키라서 상수로 두되, 이름 붙은 상수로 분리한다. |
| 3-4 | 계정 잠금으로 서비스 방해 | 잠금이 계정 단위라서, 아무나 비밀번호를 몇 번 틀려 admin을 `LOCK_MINUTES` 동안 잠글 수 있다. | 개인 앱이라 우선순위는 낮다. 선택: 잠금을 (계정, IP) 단위로 바꾼다. 3-1을 먼저 해야 의미가 있다. |
| 3-5 | 외부 XML 파싱 | `lyrics_fetch.py:89,288`이 알송 응답을 `ElementTree`로 파싱한다. | 파이썬 3.12의 expat은 엔티티 확장 공격을 기본으로 막는다. 조치하지 않고 기록만 한다. |

## 4단계 — 성능

| # | 항목 | 조치 |
|---|---|---|
| 4-1 | `i18n` 청크 268KB: ko와 en(합계 164KB)에 vue-i18n 메시지 컴파일러까지 들어 있다. | ① 안 쓰는 언어는 `import()`로 필요할 때 불러온다 (`setLocale`에서). ② 선택: `@intlify/unplugin-vue-i18n`으로 메시지를 미리 컴파일해 런타임 컴파일러를 뺀다. ①만 해도 첫 로딩이 약 70KB 줄어든다. |
| 4-2 | 메인 청크 `index-*.js` 246KB | 라우트는 이미 지연 로딩된다. 4-1 뒤에 다시 잰다. 추가 작업은 필요할 때만 한다. |

## 5단계 — DB (낮은 우선순위)

| # | 항목 | 조치 |
|---|---|---|
| 5-1 | 인덱스 없는 FK: `extract_jobs.track_id`, `extract_jobs.user_id`, `videos.added_by`, `playlists.chart_id` | 곡, 사용자, 차트를 지울 때 FK를 찾느라 테이블 전체를 훑는다. 지금은 행이 적어 체감이 없다. 마이그레이션 한 개로 인덱스 4개를 추가한다. |
| 5-2 | `artists.bio` 컬럼 | 0001부터 있었지만 한 번도 쓰지 않았다. 백업 복원은 백업 당시 스키마로 넣은 뒤 업그레이드하므로 지워도 안전하다. 이득이 작아서 5-1과 같은 마이그레이션에 넣을 때만 지운다. |
| 5-3 | 사용 안 된 인덱스 | **지우지 않는다.** 개발 DB는 곡이 65개뿐이라 `idx_scan=0`은 의미가 없다. trgm과 `search_text` 인덱스는 운영 규모에서 필요하다. |

## 6단계 — 사용자 확인 필요

| # | 항목 | 설명 |
|---|---|---|
| 6-1 | 사용자 전환 (`GET /auth/accounts`, `POST /auth/switch`) | 0.51.0에서 화면이 없어졌다. 지금은 스모크 테스트만 부른다. `login`은 여전히 다른 계정 쿠키를 쓰고(`others_on_device`), `security.py`가 이 쿠키를 처리한다. 지우면 기능 하나가 완전히 없어진다. 화면을 되살릴지, 백엔드도 지울지 정해야 한다. |
| 6-2 | 큰 파일 나누기 | `stores/player.ts` 1440줄은 이미 구역 주석으로 나뉘어 있다(라디오, 오디오북, 사운드). `scanner.py` 1284줄, `extract.py` 1238줄. 나누면 읽기는 쉬워지지만, 지금 버그가 있는 것은 아니다. "단순하게 유지" 원칙에 따라 **하지 않는 것을 권장**한다. |

---

## 점검했지만 문제가 아닌 것 (다시 조사하지 않도록)

- **"안 쓰는" 라우트로 잡혔지만 실제로 쓰는 것**
  - `/charts/{id}/folder-banner`, `/admin/banners/candidates/{token}`: 백엔드가 응답 안에 URL을 만들어 준다 (`collections.py:62,361`).
  - `/albums|tracks/{id}/videos`: `VideoSheet.vue:49`가 템플릿 문자열로 부른다.
  - `/video-playlists/{id}/transfer`: `PlaylistTransferSheet.vue:56`이 템플릿 문자열로 부른다.
- **ruff B023 (`api/videos.py:417`, `lyrics_fetch.py:289`)**: 클로저를 같은 반복 안에서 바로 호출하므로 문제없다.
- **ruff B008 333건**: FastAPI의 `Depends(...)` 기본값 관례다.
- **bandit B310**: 접속하는 곳이 고정 호스트이거나 관리자가 입력한 URL이다.
- **bandit B608 (`backup.py:299`)**: 식별자를 `information_schema`에서 가져온다.
- **bandit B324**: SHA1은 캐시 키에 쓰고, MD5는 알송 프로토콜이 요구한다. 보안 용도가 아니다.
- **npm audit (picomatch ReDoS)**: vue-tsc와 vite 같은 빌드 도구에만 들어 있고 배포 이미지에는 없다. `npm audit fix --force`는 vite를 6으로 **내리므로 실행하지 말 것.** 다음 버전 업그레이드 때 함께 해결된다.
- **pip-audit**: 알려진 취약점 0건.
- **인증**: 인증 없이 열린 라우트는 `/config`와 `/auth/*`(login, setup, signup, logout, switch)뿐이다. 모두 의도된 것이다.
- **경로 조작**:
  - 영상 파일은 `_inside()`로 검사한다.
  - 폴더 탐색은 디스크가 아니라 DB를 조회한다.
  - 추출 폴더는 `resolve()`한 뒤 부모 경로를 검사한다.
- **로그인**:
  - 없는 사용자일 때도 `dummy_verify`를 돌려서, 응답 시간으로 사용자 이름이 있는지 알아낼 수 없다.
  - 쿠키는 `httponly`, `samesite=lax`, `secure`다.
  - 만료된 세션은 로그인할 때 정리된다.
  - 활동 로그는 `KEEP_DAYS` 기준으로 정리된다.
- **N+1 쿼리**: API 핸들러에서 반복문 안에 DB 호출이 있는 곳은 `guess_track`과 `guess_album`뿐이다. 둘 다 몇 번만 돈다.
- **코드 블록 중복 (8줄 이상 같은 코드)**: 위 2-2의 제스처 코드 말고는 사실상 없다.
- **`vue-tsc`**: 오류 0건.

## 진행 순서 제안

1. 1단계와 2-1 → 패치 릴리스 한 번
2. 2-2, 2-3, 4-1 → 화면 확인 후 릴리스
3. 3단계와 5-1 → 마이그레이션 포함 릴리스
4. 6단계는 사용자 결정에 따라
