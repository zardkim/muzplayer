# Third-party notices · 제3자 고지

muzplayer is licensed under the **GNU General Public License v3.0 or later** (see [LICENSE](LICENSE)).
It builds on the open-source software below, each under its own license. The Docker image
bundles the backend libraries, ffmpeg and deno as listed.

muzplayer는 **GPL-3.0-or-later**로 배포됩니다. 아래 오픈소스를 사용하며, 각 구성 요소는 각자의
라이선스를 따릅니다.

## Backend (Python) — in the Docker image

| Package | Version | License |
|---|---|---|
| [FastAPI](https://github.com/fastapi/fastapi) | 0.162.0 | MIT |
| [Uvicorn](https://github.com/encode/uvicorn) | 0.54.0 | BSD-3-Clause |
| [SQLAlchemy](https://www.sqlalchemy.org/) | 2.1.6 | MIT |
| [Alembic](https://github.com/sqlalchemy/alembic) | 1.20.1 | MIT |
| [psycopg](https://www.psycopg.org/) | 3.3.6 | LGPL-3.0-only |
| [mutagen](https://github.com/quodlibet/mutagen) | 1.48.1 | GPL-2.0-or-later |
| [Pillow](https://python-pillow.org/) | 13.0.0 | MIT-CMU |
| [argon2-cffi](https://github.com/hynek/argon2-cffi) | 25.1.0 | MIT |
| [Beautiful Soup](https://www.crummy.com/software/BeautifulSoup/) | 4.15.0 | MIT |
| [yt-dlp](https://github.com/yt-dlp/yt-dlp) | 2026.10.26 | Unlicense |
| [yt-dlp-ejs](https://github.com/yt-dlp/ejs) | 0.8.0 | Unlicense AND MIT AND ISC |

mutagen (GPL-2.0-or-later) is the reason muzplayer itself is released under the GPL.

## Programs in the Docker image

| Program | Version | License | Notes |
|---|---|---|---|
| [FFmpeg](https://ffmpeg.org/) | 7.1.1 | LGPL-2.1-or-later | Built from the official source release without `--enable-gpl` / `--enable-nonfree`, statically linked with LAME. The exact configuration is in the [Dockerfile](Dockerfile) (stage `ffmpeg`); rebuilding the image from it reproduces the binary, and it can be replaced with another build through `FFMPEG_PATH`. |
| [LAME](https://lame.sourceforge.io/) (libmp3lame) | Debian package | LGPL-2.0-or-later | Linked into the FFmpeg binary above. |
| [Deno](https://deno.com/) | 2.9.8 | MIT | JavaScript runtime used by yt-dlp for YouTube. |
| [PostgreSQL](https://www.postgresql.org/) | 17 (official image) | PostgreSQL License | Separate container (`postgres:17-alpine`). |
| [Python](https://www.python.org/) | 3.12 (official slim image) | PSF-2.0 | Base image. |

## Frontend (bundled into the web app)

| Package | License |
|---|---|
| [Vue](https://vuejs.org/), [Vue Router](https://router.vuejs.org/), [Pinia](https://pinia.vuejs.org/), [Vue I18n](https://vue-i18n.intlify.dev/) | MIT |
| [Lucide](https://lucide.dev/) icons (`@lucide/vue`) | ISC |
| [Tailwind CSS](https://tailwindcss.com/) (build time) | MIT |
| [Pretendard](https://github.com/orioncactus/pretendard) font | SIL OFL 1.1 |
| [Space Grotesk](https://fonts.google.com/specimen/Space+Grotesk) font (loaded from Google Fonts) | SIL OFL 1.1 |

## Trademarks and external services · 상표와 외부 서비스

- The logos of radio broadcasters and music charts in `frontend/public/radio-logos/` and
  `frontend/public/logos/` (KBS, MBC, SBS, Melon, Bugs, Genie, Billboard and others) are trademarks
  of their owners. They are shown only to identify the stations and charts; muzplayer is not
  affiliated with or endorsed by them.
- Album information, ratings, artist names and lyrics are looked up from third-party services
  (Bugs, Melon, AlSong, LRCLIB, MusicBrainz, Wikidata, Wikipedia, Deezer). Some of these are
  **unofficial integrations**; they may change or stop working, and their use is subject to each
  service's terms. Use them for personal, non-commercial purposes.
- Radio streams are the broadcasters' own public streams, relayed to the listener's device.
- Taking audio out of YouTube videos is **off by default**. YouTube's terms allow downloads only
  where YouTube permits them; use it only for videos you have the rights to.

- 방송사·차트 로고는 각 소유자의 상표이며, 방송과 차트를 구분하는 용도로만 표시합니다. muzplayer는
  이들과 관계가 없습니다.
- 앨범 정보·별점·가사 등은 외부 서비스에서 가져오며, 일부는 **비공식 연동**입니다. 각 서비스의 약관을
  따르고 개인적·비상업적 용도로만 사용하세요.
- YouTube 음원 추출은 기본으로 꺼져 있습니다. 권리가 있거나 허락된 영상에만 사용하세요.
