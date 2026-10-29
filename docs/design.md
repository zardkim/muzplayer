# muzplayer 디자인

원본 캔버스(Claude Design): https://claude.ai/artifact/Y4QkhVMvWbY3L2Tv4Tufz7
보드: 브랜드 시트 · 데스크톱 앨범 · 모바일 로그인 / 홈 / 재생 화면 · 관리자

현재 적용: **v2 라이트** (캔버스의 `v2 · 라이트` 페이지). v1 다크 시안은 캔버스에 보관만 한다.
국내 음악 앱의 구성(큰 페이지 제목, 칩, 얇은 선 아이콘, 떠 있는 미니 플레이어·탭 바, 앨범 아트 중심 재생 화면)을
참고했고, 로고·색은 muzplayer 고유의 것이다.

## 로고

검정 레코드판 + 강조색 라벨 + 흰 재생 버튼. 바깥 홈(groove) 선은 48px 이상에서만 그린다.

| 파일 (`frontend/public/`) | 용도 |
|---|---|
| `logo.svg` | 로그인 화면 등 큰 로고 |
| `favicon.svg` | 브라우저 탭 |
| `app-icon.svg`, `icon-192/512.png` | PWA 아이콘 |
| `icon-maskable-512.png`, `icon-180.png` | Android 마스크 아이콘, iOS 홈 화면 |
| `cover-placeholder.svg` | 앨범 아트가 없을 때 |

## 토큰 (`frontend/src/style.css`의 `@theme`)

| 토큰 | 값 | 쓰임 |
|---|---|---|
| bg | `#FFFFFF` | 배경 |
| surface / surface-2 | `#F4F4F5` / `#EDEDEF` | 검색창·입력, 선택된 탭 |
| line / line-strong | `#E4E4E7` / `#D4D4D8` | 구분선, 칩 테두리 |
| ink | `#111113` | 본문, 기본 버튼(검정 알약) |
| muted / subtle | `#71717A` / `#A1A1AA` | 보조 글자 / 약한 아이콘 |
| accent / accent-soft | `#D93B22` / `#FDF1EE` | 재생 중인 곡, 진행 바, 로고 |
| danger | `#C8261D` | 오류 |

- 글꼴: **Pretendard**(UI, 앱에 포함), **Space Grotesk**(로고·숫자)
- 아이콘: Lucide (`@lucide/vue`), 1.2~1.4px 얇은 선
- 터치 영역 최소 44px, 버튼과 칩은 알약 모양
- 재생 화면 배경은 앨범 아트 평균색을 은은하게 번지게 한다
