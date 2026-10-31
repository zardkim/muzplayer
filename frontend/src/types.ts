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
  is_favorite: boolean
  rating?: number | null // this user's stars (0.5-5, in halves)
  year?: number | null // the album's year
  has_video?: boolean
  missing: boolean
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
  wiki: string
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
  rules: SmartRules | null
  track_count: number | null // null for a smart playlist until it is opened
  created_at: string
  updated_at: string
}

export interface PlaylistDetail extends Playlist {
  entries: { entry_id: number | null; track: Track }[] // no entry_id in a smart playlist
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

export type VideoKind = 'mv' | 'live' | 'cover' | 'other'
export interface Video {
  id: number
  youtube_id: string
  kind: VideoKind
  title: string
  channel: string
  album_id: number | null
  track_id: number | null
  can_edit: boolean
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
