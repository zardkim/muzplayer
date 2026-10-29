export interface Track {
  id: number
  title: string
  artist: string
  artist_id: number | null
  album: string
  album_id: number | null
  has_cover: boolean
  track_no: number | null
  disc_no: number | null
  duration: number | null
  format: string
  is_favorite: boolean
  missing: boolean
}

export interface Album {
  id: number
  title: string
  artist: string
  artist_id: number | null
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
}

export interface Page<T> {
  items: T[]
  total: number
}
