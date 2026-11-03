/** Another account signed in on this device (user switching). */
export interface Account {
  id: number
  username: string
  display_name: string
  is_admin: boolean
}

export interface Track {
  id: number
  title: string
  artist: string
  artist_id: number | null
  album: string
  album_id: number | null
  album_kind?: AlbumKind
  has_cover: boolean
  cover_v?: number // the album's cover version: part of the cover URL (missing in queues saved by 0.5)
  track_no: number | null
  disc_no: number | null
  duration: number | null
  format: string
  sample_rate?: number // Hz; 0 = unknown
  bit_depth?: number // lossless files only; 0 = lossy or unknown
  bitrate?: number // kbps
  popular?: boolean // in an album: one of its most played songs (everyone's plays)
  rg?: [number | null, number | null, number | null, number | null] | null // ReplayGain: track gain, peak, album gain, peak
  is_favorite: boolean
  rating?: number | null // this user's stars (0.5-5, in halves)
  year?: number | null // the album's year
  has_video?: boolean
  has_lyrics?: boolean // lyrics (synced or plain): its own (tags, .lrc next to it) or fetched for it
  missing: boolean
  scan_error?: string | null // the last scan could not read the file again (it plays as read before)
  damaged?: boolean // an MP3 only ffmpeg could read: played converted (server transcode)
  chart_position?: number | null // only in chart lists
}

export type AlbumKind = 'album' | 'unofficial' | 'compilation' | 'soundtrack' | 'chart'

export interface Album {
  id: number
  title: string
  artist: string
  artist_id: number | null
  kind: AlbumKind
  year: number | null
  release_date?: string | null // YYYY-MM-DD when a tag has the whole date
  quality?: 'hires' | 'lossless' | null
  has_cover: boolean
  cover_v: number
  track_count: number
}

export interface AlbumDetail extends Album {
  tracks: Track[]
  rating: number | null // this user's stars for the album itself
  track_rating_avg: number | null // average of this user's stars for its songs
  is_favorite: boolean
  video_count: number
  description: string | null // its introduction (eztag album card, Bugs/Melon, or written by an admin)
  description_source: string | null // eztag | bugs:<id> | melon:<id> | manual
}

export interface Artist {
  id: number
  name: string
  album_count: number
  track_count: number
  image_v: number // 0 = no photo
}

export interface ArtistDetail {
  id: number
  name: string
  image_v: number
  image_credit: { wiki: string; title: string; url: string } | null // a Wikipedia photo's article
  image_removed: boolean // an admin removed the photo: lookups leave it alone
  albums: Album[]
  tracks: Track[]
}

export interface ArtistImageCandidate {
  source: 'melon' | 'bugs' | 'apple' | 'ko' | 'en' // a music site, or Wikipedia in that language
  title: string
  description: string
  image: string
  url: string
}

export type CollectionKind = 'chart' | 'theme'

/** Where the banner image comes from; null on a collection means the page draws one from covers. */
export interface CollectionBanner {
  url: string
  kind: 'ai' | 'folder'
  scope: 'collection' | 'source'
  id: number | null
}

/** A chart week or a theme. source: the chart's source (멜론), or the theme's category (may be empty). */
export interface Chart {
  id: number
  kind: CollectionKind
  title: string
  source: string
  track_count: number
  cover_albums: { id: number; v: number }[] // best ranked first, for the cover and the auto banner
  banner: CollectionBanner | null
  created_at: string
}

export interface ChartDetail extends Chart {
  tracks: Track[]
  shared_playlist_id: number | null // the shared playlist made from it (the newest)
}

export interface CollectionsHome {
  hero: Chart[]
  sources: { source: string; total: number; items: Chart[] }[]
  picks: Chart[]
  categories: { category: string; total: number; items: Chart[] }[]
  recent: Chart[]
  counts: { charts: number; themes: number }
}

export type FolderKind = 'album' | 'compilation' | 'chart' | 'theme' | 'excluded'

export interface LibraryFolder {
  path: string
  kind: FolderKind
  suggested: FolderKind | null
  track_count: number
  present: boolean
  audiobooks: boolean // the library/audiobook folder: never scanned as music
}

export interface Lyrics {
  synced: [number, string][] | null // [seconds, line], sorted
  plain: string | null
}

export interface BookProgress {
  position: number // seconds on the whole-book timeline
  finished: boolean
  updated_at: string
}

export interface Book {
  id: number
  title: string
  subtitle: string
  authors: string
  narrators: string
  series: string
  series_seq: string
  published_year: number | null
  duration: number
  has_cover: boolean
  cover_v?: number
  chapter_count: number
  created_at: string
  progress: BookProgress | null
}

export interface Chapter {
  start: number
  end: number
  title: string
}

export interface BookDetail extends Book {
  description: string
  genres: string[]
  publisher: string
  language: string
  isbn: string
  asin: string
  chapters: Chapter[]
  files: { duration: number; offset: number }[] // play order; offset = start on the book timeline
}

export interface Genre {
  id: number
  name: string
  track_count: number
  covers?: { id: number; v: number }[] // its biggest albums, for the genre tiles
}

export interface Folder {
  name: string
  path: string // from the library root, '/'-separated
  track_count: number // songs in it and below
  cover: { id: number; v: number } | null
}

export interface FolderListing {
  path: string
  folders: Folder[]
  tracks: Track[] // directly in the folder, by file name
}

export interface Playlist {
  id: number
  name: string
  kind: 'manual' | 'smart'
  is_default?: boolean // each person's own default list: always there, first, can't be deleted
  is_shared?: boolean // everyone sees and plays it (charts & themes page, home)
  chart_id?: number | null // the chart or theme it was made from
  owner?: string // who made it (the shared list)
  rules: SmartRules | null
  track_count: number | null // null for a smart playlist until it is opened
  cover?: { id: number; v: number } | null // its first song's album cover (the list's card)
  created_at: string
  updated_at: string
}

export interface PlaylistDetail extends Playlist {
  entries: { entry_id: number | null; track: Track }[] // no entry_id in a smart playlist
  can_edit: boolean // its maker (or, a shared one, an admin); others only listen
}

export type RuleField = 'genre' | 'artist' | 'year' | 'rating' | 'favorite' | 'plays' | 'last_played' | 'added' | 'folder' | 'duration'
export interface SmartRule {
  field: RuleField
  op: string
  value: string | number | boolean | number[] | null
}
export interface SmartRules {
  match: 'all' | 'any'
  rules: SmartRule[]
  sort: 'random' | 'plays' | 'recent' | 'title' | 'rating' | 'last_played'
  limit: number
}

export interface Mix {
  key: string
  track_count: number
  cover_albums: { id: number; v: number }[]
}

export type VideoKind = 'mv' | 'concert' | 'tv' | 'fan' | 'other'
export const VIDEO_KINDS: VideoKind[] = ['mv', 'concert', 'tv', 'fan', 'other']
export interface Video {
  id: number
  source: 'youtube' | 'file' // a file: in library/video on the NAS
  youtube_id: string | null
  file_path: string | null
  duration?: number | null // seconds, NAS files
  kind: VideoKind
  title: string
  channel: string
  album_id: number | null
  track_id: number | null
  can_edit: boolean
}
/** A video on the Music videos page, with the song or album it was added to. */
export interface VideoListItem extends Video {
  created_at: string
  target: { type: 'track' | 'album'; title: string; artist: string; album_id: number | null; has_cover: boolean; cover_v: number } | null
  is_favorite?: boolean // this person liked it
}
/** A person's video playlist (and, opened, its videos). */
export interface VideoPlaylist {
  id: number
  name: string
  count: number
  thumb: string | null // the first YouTube video's id, for a picture
  is_default?: boolean // as Playlist.is_default
  entries?: { entry_id: number; video: VideoListItem }[]
}
/** A video file in library/video (the NAS), registered or not. */
export interface VideoFile {
  path: string
  size: number
  video_id: number | null
  linked?: string // just registered: the song it was linked to ("title · artist")
}
export interface VideoResult {
  youtube_id: string
  title: string
  channel: string
  published_at: string | null
  duration: number | null
  added: boolean
}

export interface User {
  id: number
  username: string
  display_name: string
  is_admin: boolean
  is_active: boolean
  record_history: boolean // off: plays leave no history or play count
  home_sections: { key: string; on: boolean }[] | null // home rows in order; null = the default
  prefs?: Record<string, unknown> | null // the app's settings kept with the account (prefsSync.ts)
  pending?: boolean // signed up, waiting for an admin to approve
  created_at?: string | null
  last_login_at?: string | null
  last_seen_at?: string | null // admin list: the last request
  online?: boolean // admin list: seen in the last few minutes
}

export interface ActivityEntry {
  id: number
  at: string
  user_id: number | null
  username: string
  action: string // login | logout | switch | setup | signup | password_changed | login_failed | login_locked | admin
  detail: string
  ip: string
}

export interface ScanJob {
  id: number
  status: 'running' | 'done' | 'failed' | 'cancelled'
  started_at: string
  finished_at: string | null
  scanned: number
  added: number
  updated: number
  missing: number
  errors: number
  error_summary: string | null
  books_added: number
  books_updated: number
  books_missing: number
  folder: string | null // one top-level folder; null = the whole library
  mode: 'scan' | 'rescan' | 'reset'
}

export interface Page<T> {
  items: T[]
  total: number
}

/** How a list page shows its items: list (목록형), cover (커버형: big artwork), grid (격자형: small artwork). */
export type ViewMode = 'list' | 'cover' | 'grid'

/** A live radio station (backend radio.py; the list comes from radio.bsod.kr). */
export interface RadioStation {
  id: string
  name: string
  stn: string // broadcaster: kbs, mbc, sbs, cbs, ...
  regions: string[] // seoul, busan, ...
  logo: string | null // /radio-logos/<logo>.png (from Wikipedia/Commons); none: the badge
}
