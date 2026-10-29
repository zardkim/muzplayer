# muzplayer

NAS 음악 폴더를 가족·지인이 각자 계정으로 듣는 개인용 웹 음악 플레이어.
FastAPI + PostgreSQL + Vue 3, 컨테이너 2개(app, db). 한국어(기본)·영어 UI.

- 계획서: [music_player_plan.md](music_player_plan.md)
- 디자인: [docs/design.md](docs/design.md)

## NAS 배포 (빌드 없음 — 이미지 pull + `.env`)

1. NAS에 폴더를 만들고 두 파일을 복사한다.
   ```
   /volume1/docker/muzplayer/
   ├── docker-compose.yml   ← deploy/docker-compose.yml (수정하지 않음)
   └── .env                 ← deploy/.env.example 을 복사해 값 입력
   ```
2. Harbor 로그인 (deploy 로봇, 최초 1회)
   ```bash
   echo '<시크릿>' | docker login harbor.nurilab.pe.kr -u 'robot$muzplayer+deploy' --password-stdin
   ```
   - `MUSIC_PATH`: 음악 폴더. 안에 있는 심볼릭 링크 폴더(`ln -s`)와 마운트된 공유 폴더도 스캔한다.
   - `MUSIC_ROOT`: 컨테이너에 같은 경로로 읽기 전용 연결할 폴더. 보통 `MUSIC_PATH`와 같게 두고,
     링크가 음악 폴더 밖(예: `/volume1/다른폴더`)을 가리키면 둘을 모두 포함하는 상위 폴더(`/volume1`)로 둔다.
   - `SCAN_INTERVAL_MINUTES`: 자동 재스캔 주기(기본 60분, 0이면 수동만).
3. 실행: `docker compose up -d`
   - 시작할 때 DB 마이그레이션과 최초 관리자 생성(`ADMIN_USERNAME`/`ADMIN_PASSWORD`)이 자동으로 된다.
   - 관리자로 로그인 → 관리자 화면에서 **스캔 시작**. 이후 `.env`의 `ADMIN_PASSWORD`는 지워도 된다.
4. 업데이트: `.env`의 `MUZPLAYER_VERSION` 변경 → `docker compose pull && docker compose up -d`
   - **0.1.x → 0.2.0:** 새 `docker-compose.yml`로 교체하고 `.env`에 `MUSIC_ROOT`(보통 `MUSIC_PATH`와 같은 값)를 추가한다.
5. 휴대폰에서 앱처럼 쓰기(PWA): iPhone은 Safari 공유 → **홈 화면에 추가**, Android Chrome은 설정 화면의 **앱으로 설치**.

### 라이브러리 링크·마운트

- 스캔은 링크된 폴더를 따라가고, 같은 파일이 두 경로로 보이면 한 번만 등록한다. 순환 링크는 한 번만 방문한다.
- 끊긴 링크나 읽을 수 없는 폴더(오프라인 공유 등)는 스캔 오류로 표시하고, 그 아래 곡은 **누락 처리하지 않는다.**
- 음악 폴더 전체가 비어 보이면(마운트 해제 등) 스캔을 실패로 끝내고 아무것도 숨기지 않는다.
- 앱 실행 중에 새로 마운트한 공유는 앱 재시작 후 보인다. 바로 보이게 하려면 `MUSIC_MOUNT_PROPAGATION=rslave`
  (NAS 쪽 마운트가 shared여야 하며, 앱이 시작되지 않으면 `rprivate`로 되돌린다).

역방향 프록시는 `http://<NAS>:${HTTP_PORT}`로 연결한다. HTTPS 없이 IP로 직접 테스트할 때만
`COOKIE_SECURE=false`.

## 백업·복구

DB에 사용자 계정·플레이리스트·즐겨찾기·재생 기록이 모두 들어 있다. 앨범 아트 캐시는 재스캔으로 다시 만들어진다.

Synology 작업 스케줄러(매일, root)에 등록:
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

## 빌드 (개발서버)

```bash
./build.sh 0.1.0     # harbor.nurilab.pe.kr/muzplayer/muzplayer:0.1.0 + latest 푸시
```

`build.sh`는 `DOCKER_CONFIG=~/.docker-harbor/muzplayer`(로봇 `robot$muzplayer+ci`)를 쓴다.

## 로컬 개발

```bash
python3 -m venv .venv && .venv/bin/pip install -r backend/requirements.txt
docker run -d --name muz-devdb -e POSTGRES_USER=muzplayer -e POSTGRES_PASSWORD=devpass \
  -e POSTGRES_DB=muzplayer -p 127.0.0.1:15499:5432 postgres:17-alpine

cd backend
export DATABASE_URL=postgresql+psycopg://muzplayer:devpass@127.0.0.1:15499/muzplayer \
       MUSIC_DIR=/path/to/music DATA_DIR=/tmp/muzdata COOKIE_SECURE=false \
       ADMIN_USERNAME=admin ADMIN_PASSWORD=adminpass1
../.venv/bin/alembic upgrade head && ../.venv/bin/python -m app.bootstrap
../.venv/bin/uvicorn app.main:app --port 18580 --reload

cd ../frontend && npm install && npm run dev      # http://localhost:5173 (/api → 18580)
```

- 모델 변경 후: `alembic revision --autogenerate -m "..."`
- UI 문구는 `frontend/src/locales/ko.json`·`en.json`에 같은 키로 추가한다(`npm run build`가 키 불일치를 막는다).
- API 점검: `scripts/smoke_test.sh <url> <admin> <password> <음악폴더>` — **테스트용 음악 폴더에만** 쓴다
  (파일 하나를 잠시 옮겼다 되돌리고, 비활성 `smokeuser` 계정을 남긴다).
