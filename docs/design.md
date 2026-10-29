# muzplayer 디자인

원본 캔버스(Claude Design): https://claude.ai/artifact/Y4QkhVMvWbY3L2Tv4Tufz7
보드: 브랜드 시트 · 데스크톱 앨범 · 모바일 로그인 / 홈 / 재생 화면 · 관리자

## 로고

레코드판 + 재생 버튼. 바깥 홈(groove) 선은 48px 이상에서만 그린다.

| 파일 (`frontend/public/`) | 용도 |
|---|---|
| `logo.svg` | 로그인 화면 등 큰 로고 |
| `favicon.svg` | 브라우저 탭 |
| `app-icon.svg`, `icon-180/192/512.png` | 홈 화면 아이콘(iOS), Media Session 기본 아트 |
| `cover-placeholder.svg` | 앨범 아트가 없을 때 |

## 토큰 (`frontend/src/style.css`의 `@theme`)

| 토큰 | 값 | 쓰임 |
|---|---|---|
| bg | `#0E1013` | 배경 |
| sidebar | `#0B0D10` | 데스크톱 사이드바 |
| surface / surface-2 | `#171A1F` / `#20242B` | 카드, 입력, 선택 행 |
| line / line-strong | `#2A2F37` / `#3A404A` | 구분선, 보조 버튼 테두리 |
| ink / muted / subtle | `#F2EFE9` / `#A3A9B3` / `#7D848F` | 본문 / 보조 / 아주 약한 글자 |
| accent / accent-strong | `#F5A524` / `#FFC35C` | 재생 상태, 주요 버튼, 진행 바 (강조색 위 글자는 bg) |
| danger | `#F07167` | 오류 |

- 글꼴: **IBM Plex Sans KR**(UI 전체), **Space Grotesk**(로고·숫자·시간)
- 아이콘: Lucide (`@lucide/vue`), 2px 선
- 버튼·터치 영역 최소 44px, 주요 버튼은 pill 형태
- 다크 테마 단일
