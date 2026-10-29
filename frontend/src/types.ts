export interface Track {
  id: number
  title: string
  artist: string
  artist_id: number | null
  album: string
  album_id: number | null
  album_kind?: AlbumKind
  has_cover: boolean
  track_no: number | null
  disc_no: number | null
  duration: number | null
  format: string
  is_favorite: boolean
  missing: boolean
  chart_position?: number | null // only in chart lists
}

export type AlbumKind = 'album' | 'unofficial' | 'compilation' | 'chart'

export interface Album {
  id: number
  title: string
  artist: string
  artist_id: number | null
  kind: AlbumKind
  year: number | null
  has_cover: boolean
  track_count: number
}

export interface AlbumDetail extends Album {
  tracks: Track[]
}

export interface Artist {
  id: number
  name: string
  album_count: number
  track_count: number
}

export interface ArtistDetail {
  id: number
  name: string
  albums: Album[]
  tracks: Track[]
}

export interface Chart {
  id: number
  title: string
  source: string
  track_count: number
  cover_album_id: number | null
}

export interface ChartDetail {
  id: number
  title: string
  source: string
  track_count: number
  tracks: Track[]
}

export type FolderKind = 'album' | 'compilation' | 'chart' | 'excluded'

export interface LibraryFolder {
  path: string
  kind: FolderKind
  suggested: FolderKind | null
  track_count: number
  present: boolean
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
}

export interface Playlist {
  id: number
  name: string
  track_count: number
  created_at: string
  updated_at: string
}

export interface PlaylistDetail extends Playlist {
  entries: { entry_id: number; track: Track }[]
}

export interface User {
  id: number
  username: string
  display_name: string
  is_admin: boolean
  is_active: boolean
}

export interface ScanJob {
  id: number
  status: 'running' | 'done' | 'failed'
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
}

export interface Page<T> {
  items: T[]
  total: number
}
