# 뮤직 영상 앨범 연결 계획서

- **작성일:** 2026-11-16
- **대상 버전:** 0.73.0
- **상태:** 구현 완료 (0.73.0 릴리스 전)

## 1. 목표

뮤직 영상 페이지에서 영상을 **곡**뿐 아니라 **앨범**에도 연결할 수 있게 한다. 한 곡이 아니라 앨범 전체에 해당하는 영상이 대상이다.

- 앨범 전곡 라이브, 쇼케이스, 콘서트 실황
- 하이라이트 메들리, 앨범 트레일러·티저
- 앨범 메이킹·다큐멘터리

연결하면 영상 카드에 앨범(커버·제목·가수)이 보이고, 누르면 앨범 페이지로 간다. 앨범 페이지에는 그 앨범의 영상 줄이 생긴다. 이 영상으로 음원을 추출할 때 앨범 이름과 가수가 태그 후보로 쓰인다.

## 2. 지금 상태 (0.72.1 코드 기준)

앨범 연결은 DB와 API에 이미 반쯤 들어 있다. 곡 연결 화면에서 고를 수만 없다.

| 부분 | 현재 | 앨범 연결에 필요한 것 |
|---|---|---|
| DB `videos` | `album_id`·`track_id` 둘 다 있음. CHECK `num_nonnulls(album_id, track_id) <= 1`, UNIQUE `(album_id, youtube_id)` | **그대로.** 마이그레이션 없음 |
| `POST /videos` (YouTube 등록) | `album_id`를 받음(앨범 영상 창에서 쓰던 경로) | 그대로 |
| `POST /videos/files` (NAS 영상 등록) | `album_id`를 받지만 화면에서는 보내지 않음 | 그대로 |
| `POST /videos/{id}/link` (곡 연결) | `track_id`만 받음. 저장할 때 `album_id`를 비움. 앨범에 붙은 YouTube 영상은 `not_a_file`로 거부 | **`album_id` 추가**(3.1) |
| 목록 응답 `list_item` | `target.type`이 `track`·`album` 둘 다 처리 | 그대로 |
| `VideoCard.vue` | 앨범 대상이면 '앨범 · 가수' 칩과 앨범 링크를 이미 그림 | 메뉴 항목만 추가 |
| `VideoLinkSheet.vue` | 곡 검색(`/tracks?q=`)과 고르기만 있음 | **곡·앨범 탭**(3.2) |
| 앨범 페이지 | 0.19.0에서 '영상' 버튼을 지움("영상은 곡마다"). `GET /albums/{id}`의 `video_count`는 보내지만 화면에서는 안 씀 | **앨범 영상 줄**(3.3) |
| 스캔의 앨범 정리(`scanner.py` `carry_album_marks`) | 앨범이 새 id로 바뀌면 영상을 `Video.youtube_id.not_in(taken)` 조건으로 옮김 | **버그 수정 필요**(3.4) |
| 음원 추출(`extract.py`) | 영상의 곡이 없으면 `album_id`의 앨범을 태그 후보로 이미 씀 | 그대로 |

현재 DB(개발): 곡 연결 6개, 연결 없음 12개, 앨범 연결 0개.

## 3. 설계

### 3.1 API — `POST /videos/{id}/link`

```python
class LinkIn(BaseModel):
    track_id: int | None = None  # 고른 곡
    album_id: int | None = None  # 고른 앨범 (새로 추가)
    auto: bool = False           # 이름으로 곡 찾기; 아무것도 없으면 연결 해제
    # track_id와 album_id는 둘 중 하나만 (model_validator, 둘 다면 422)
```

- `album_id`가 오면 앨범이 있는지 확인한다. 없거나 차트용 숨은 앨범(`kind == 'chart'`)이면 404 `not_found`이다. 그다음 `video.album_id, video.track_id = album_id, None`으로 저장한다.
- `not_a_file` 제한(앨범에 붙은 YouTube 영상은 다시 연결하지 못함)은 없앤다. 연결을 바꿀 수 있는 사람은 이미 관리자뿐이다(`_editable`). 예전 앨범 영상 창으로 등록한 영상도 곡이나 다른 앨범으로 옮길 수 있어야 한다.
- 이미 그 앨범에 같은 YouTube 영상이 있으면 지금처럼 409 `video_exists`이다(UNIQUE `(album_id, youtube_id)`).
- 응답은 지금처럼 `list_item`이고, `target.type == 'album'`이 들어 있다.

### 3.2 화면 — 연결 시트

`VideoCard.vue`의 ⋮ 메뉴:

| 지금 | 바뀐 뒤 |
|---|---|
| 곡 연결 | 곡 연결 |
| — | **앨범 연결** |
| 곡 연결 해제 (곡이 있을 때) | **연결 해제** (곡이나 앨범이 있을 때) |

- 메뉴를 보이는 조건 `video.file_path || !video.album_id`는 없앤다. 관리자에게는 모든 영상에 보인다.
- `VideoLinkSheet.vue` 위쪽에 탭 두 개, **곡 | 앨범**을 둔다. 메뉴에서 고른 쪽으로 열리고, 이미 앨범에 붙은 영상은 앨범 탭으로 열린다.
  - 앨범 탭은 `GET /albums?q=<검색어>&limit=30`을 쓴다. 이 검색은 앨범 제목, 가수, 가수의 다른 이름을 찾는다. 결과마다 커버, 앨범 제목, 가수 · 연도를 보여 준다.
  - 첫 검색어: 곡 탭은 지금처럼 영상 제목에서 [MV]·(Official Video) 같은 꼬리표를 뗀 것이다. 앨범 탭은 같은 정리에 `콘서트|concert|live|showcase|쇼케이스|full album|하이라이트|highlight medley|trailer` 같은 낱말도 더 뗀다. NAS 파일이면 상위 폴더 이름도 후보로 둔다.
  - 지금 연결된 앨범은 곡 탭처럼 강조한다(`bg-accent-soft`).
- `ui.videoLink`에 `{ ..., tab: 'track' | 'album' }`을 더한다. 끝나면 `ui.videoLinked++`로 목록을 새로 고친다(지금과 같음).
- 알림 문구는 '앨범에 연결: {album}'이다. 해제하면 '연결을 해제했습니다'이다.

새 문구 키 (ko/en):

| 키 | ko | en |
|---|---|---|
| `videos.linkAlbum` | 앨범 연결 | Link to album |
| `videos.linkAlbumHint` | 앨범 제목이나 가수를 입력하고, 연결할 앨범을 고르세요. | Type an album or artist, then pick the album. |
| `videos.linkAlbumSearch` | 앨범 검색 | Search albums |
| `videos.linkedToAlbum` | 앨범에 연결: {album} | Linked to album: {album} |
| `videos.linkTabTrack` / `linkTabAlbum` | 곡 / 앨범 | Song / Album |

`videos.unlink`는 '곡 연결 해제'에서 '연결 해제'로, `videos.unlinked`는 '연결을 해제했습니다'로 바꾼다.

### 3.3 앨범 페이지 — 앨범 영상 줄

0.19.0에서 앨범 페이지의 '영상' 버튼을 지웠다(변경 이력: "영상은 곡마다"). 앨범 연결이 생기면 앨범 영상을 볼 곳이 다시 필요하다. 그래서 버튼이 아니라 **영상이 있을 때만** 보이는 줄로 넣는다.

- 위치는 곡 목록 아래, 앨범 소개 위이다. 제목은 '앨범 영상'(`videos.forAlbum`, 이미 있는 키)이다.
- `VideoRow.vue`를 쓴다. `album-id` prop을 더하면 `GET /videos?album_id=`로 목록을 받는다. 누르면 그 줄을 이어 재생한다(`ui.videoQueue`, 홈의 영상 줄과 같음).
- 서버의 `GET /videos`에 `album_id` 쿼리를 더한다. 조건은 `Video.album_id == album_id`이다. 이렇게 하면 `list_item` 형식(썸네일, 좋아요, 대상)을 그대로 받는다.
- 곡에 연결된 영상은 지금처럼 곡 목록의 YouTube 아이콘으로 보인다. 앨범 줄에 같이 넣지는 않는다(중복).
- 앨범 페이지에서 바로 영상을 추가하는 버튼(회색 버튼, 빈 창)은 다시 만들지 않는다. 추가와 연결은 뮤직 영상 페이지에서 한다.
- 이제 `video_count`가 0이면 줄 요청 자체를 하지 않는다.

### 3.4 스캔 — 앨범이 바뀔 때 영상 옮기기 (버그 수정)

`scanner.py` `carry_album_marks`의 앨범 이전 코드:

```python
taken = select(Video.youtube_id).where(Video.album_id == new)
db.execute(update(Video).where(Video.album_id == old, Video.youtube_id.not_in(taken)).values(album_id=new))
```

NAS 파일 영상은 `youtube_id`가 NULL이다. SQL에서 `NULL NOT IN (...)`은 참이 아니어서 **옮겨지지 않는다.** 그다음 옛 앨범이 지워지면 `ON DELETE CASCADE`로 **영상 등록이 같이 지워진다.** 파일은 남는다. 또 새 앨범에 NAS 영상이 하나라도 있으면 `taken`에 NULL이 섞여 YouTube 영상까지 하나도 옮겨지지 않는다.

지금은 앨범에 붙은 NAS 영상이 없어서 드러나지 않았다. 앨범 연결을 열면 생기는 문제라 같은 버전에서 고친다.

```python
taken = select(Video.youtube_id).where(Video.album_id == new, Video.youtube_id.is_not(None))
db.execute(update(Video).where(
    Video.album_id == old,
    or_(Video.youtube_id.is_(None), Video.youtube_id.not_in(taken)),
).values(album_id=new))
```

- 옮기지 못한 YouTube 영상(새 앨범에 같은 영상이 이미 있음)은 지금처럼 옛 앨범과 함께 지워진다. 중복이므로 괜찮다.
- 앨범이 아예 없어지는 경우(곡이 전부 지워짐)도 있다. 이때 앨범에 붙은 영상은 지금처럼 CASCADE로 지워진다. NAS 영상은 등록만 지워지고 파일은 남으므로, 뮤직 영상 → 로컬 영상 등록에서 다시 등록할 수 있다. **대안:** FK를 `ON DELETE SET NULL`로 바꿔 '연결 없음'으로 남긴다. 그러려면 마이그레이션이 필요하고, 같은 YouTube 영상이 연결 없이 남으면 `ux_videos_youtube_alone`과 충돌할 수 있다. 1단계에서는 하지 않는다.

### 3.5 그 밖에 따라오는 것

- **검색:** `_matches`가 이미 `Album.title`과 앨범 가수로 찾는다. 앨범에 연결한 영상은 앨범 이름으로도 검색된다.
- **정렬 '가수순':** 이미 곡 가수 → 앨범 가수 → 채널 순이다.
- **비슷한 영상** (`/videos/{id}/related`): 앨범 영상의 장르를 이미 앨범 곡들의 장르로 잡는다.
- **음원 추출:** 앨범 영상이면 앨범과 가수가 태그 후보로 들어간다(곡 이름은 벅스 검색과 직접 입력).

### 3.6 자동 연결 (`guess_album`)

YouTube 링크로 추가할 때(`auto`)와 NAS 영상을 등록할 때, 지금처럼 **곡을 먼저** 찾는다(`guess_track`). 곡이 없으면 앨범을 찾는다.

- 후보 이름은 영상 제목, 파일 이름, 상위 폴더 이름이다. '가수 - 앨범'은 양쪽 순서를 다 본다. 폴더가 가수이고 파일이 앨범인 경우도 본다.
- [MV]·(Official Video) 같은 꼬리표를 뗀 이름이 앨범 제목과 **정확히 같아야** 한다(대소문자, 문장부호, 띄어쓰기는 무시).
- 이름에 가수가 있으면 앨범 가수와도 맞아야 한다.
- 맞는 앨범이 **하나일 때만** 연결한다. 같은 제목이 여러 개면 연결하지 않는다. 차트용 숨은 앨범은 제외한다.
- 아무것도 맞지 않으면 연결 없이 등록된다(`video_no_song`). 관리자가 직접 연결한다.

예: `아이유 - Palette`, `콘서트/Palette.mp4`, `아이유/Palette.mp4`는 'Palette'(아이유)에 연결된다. `Palette Live`, `Palette (Deluxe)`, `BTS - Palette`, `Palett`은 연결되지 않는다.

## 4. 하지 않는 것

- **이름이 조금이라도 다른 앨범의 자동 연결.** 자동 연결(3.6)은 이름이 앨범 제목과 정확히 같을 때만 한다. 비슷한 앨범('Palette Live', 'Palette (Deluxe)', 다른 가수의 같은 제목)에는 붙이지 않는다. 연결되지 않은 영상은 관리자가 ⋮ → 앨범 연결로 직접 고른다(2026-11-16 결정).
- **영상 하나를 곡과 앨범에 동시에 연결.** DB 제약(`<= 1`)을 유지한다. 한 곡의 뮤직비디오는 곡에, 앨범 전체 영상은 앨범에 붙인다.
- **영상 하나를 여러 앨범에 연결**(디럭스판·리패키지). 같은 YouTube 영상은 앨범마다 따로 등록할 수 있다(UNIQUE가 앨범별). NAS 파일은 `file_path` UNIQUE라 한 곳에만 연결된다.
- 일반 사용자의 연결 권한. 지금처럼 관리자만 바꾼다.

## 5. 작업 순서

| # | 작업 | 파일 |
|---|---|---|
| 1 | `LinkIn.album_id`, 둘 중 하나 검사, 차트 앨범 거부, `not_a_file` 제거 | `backend/app/api/videos.py` |
| 2 | `GET /videos?album_id=` | `backend/app/api/videos.py` |
| 3 | 앨범 이전 NULL 버그 수정 | `backend/app/scanner.py` |
| 4 | ⋮ 메뉴: 앨범 연결·연결 해제, 보이는 조건 | `frontend/src/components/VideoCard.vue` |
| 5 | 연결 시트 곡·앨범 탭, 앨범 검색, 첫 검색어 | `frontend/src/components/VideoLinkSheet.vue`, `stores/ui.ts` |
| 6 | 앨범 페이지 영상 줄 (`VideoRow`에 `albumId`) | `frontend/src/views/AlbumView.vue`, `components/VideoRow.vue` |
| 7 | 문구 ko/en | `frontend/src/locales/*.json` |
| 8 | 스모크 테스트 추가 | `scripts/smoke_test.sh` |

## 6. 확인

**스모크 테스트에 추가 (5개):**

1. 앨범에 연결하면 `target.type == 'album'`이고 `album_id`가 있으며 `track_id`가 null이다.
2. `track_id`와 `album_id`를 같이 보내면 422이다.
3. 차트 앨범이나 없는 앨범은 404이다.
4. 일반 사용자는 403이다.
5. `GET /videos?album_id=`가 그 앨범의 영상만 돌려준다.

**스캔:**

- 앨범에 NAS 영상과 YouTube 영상을 하나씩 붙인다. 앨범 태그를 바꿔 다시 스캔하면 둘 다 새 앨범 id로 옮겨 가야 한다.
- 새 앨범에 이미 NAS 영상이 있을 때도 옛 앨범의 YouTube 영상이 옮겨 가야 한다.

**화면 (휴대폰·PC):**

- ⋮ → 앨범 연결 → 검색 → 고르기 → 카드에 '앨범 · 가수' 칩이 나오고, 칩을 누르면 앨범 페이지로 간다.
- 앨범 페이지 '앨범 영상' 줄에서 재생하면 다음 영상으로 이어진다. 영상이 없는 앨범에는 줄이 없다.
- 곡에 붙은 영상을 앨범으로 옮기면 곡 목록의 YouTube 아이콘이 사라진다.

## 7. 일정

| 단계 | 내용 | 예상 |
|---|---|---|
| 1 | API·스캔 수정·스모크 | 0.5일 |
| 2 | 연결 시트·메뉴·앨범 페이지 줄 | 0.5일 |
| 3 | 화면 확인, 릴리스 0.73.0 | 0.5일 |
