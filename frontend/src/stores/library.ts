import { defineStore } from 'pinia'
import { reactive, ref } from 'vue'
import { api } from '../api'
import type { Playlist, Track, VideoPlaylist } from '../types'

/** Shared per-user state used across views: likes and stars set here (overriding what lists
 * loaded earlier say) and the playlist list. */
export const useLibrary = defineStore('library', () => {
  // track lists come from many endpoints; local toggles override their is_favorite flag
  const favoriteOverrides = reactive(new Map<number, boolean>())
  const ratingOverrides = reactive(new Map<number, number | null>())
  const playlists = ref<Playlist[]>([])
  const sharedPlaylists = ref<Playlist[]>([]) // everyone's (the sidebar and the playlists page)
  const videoPlaylists = ref<VideoPlaylist[]>([]) // the sidebar, My Music, the playlists page and the video picker

  function isFavorite(track: Track) {
    return favoriteOverrides.get(track.id) ?? track.is_favorite
  }

  async function toggleFavorite(track: Track) {
    const next = !isFavorite(track)
    favoriteOverrides.set(track.id, next)
    try {
      await api(`/favorites/${track.id}`, { method: next ? 'PUT' : 'DELETE' })
    } catch (e) {
      favoriteOverrides.set(track.id, !next)
      throw e
    }
  }

  function rating(track: Track) {
    return ratingOverrides.has(track.id) ? ratingOverrides.get(track.id)! : (track.rating ?? null)
  }

  /** 1-5 stars, or null to clear. */
  async function rate(track: Track, stars: number | null) {
    const before = rating(track)
    ratingOverrides.set(track.id, stars)
    try {
      await api(`/ratings/tracks/${track.id}`, stars ? { method: 'PUT', body: { rating: stars } } : { method: 'DELETE' })
    } catch (e) {
      ratingOverrides.set(track.id, before)
      throw e
    }
  }

  async function loadPlaylists() {
    const [mine, shared] = await Promise.all([
      api<{ items: Playlist[] }>('/playlists'),
      api<{ items: Playlist[] }>('/playlists/shared').catch(() => ({ items: sharedPlaylists.value })),
    ])
    playlists.value = mine.items
    sharedPlaylists.value = shared.items
  }

  async function loadVideoPlaylists() {
    videoPlaylists.value = (await api<{ items: VideoPlaylist[] }>('/video-playlists')).items
  }

  async function createPlaylist(name: string) {
    const p = await api<Playlist>('/playlists', { method: 'POST', body: { name } })
    await loadPlaylists()
    return p
  }

  /** Songs already in the list are not added twice: {added, skipped}. */
  async function addToPlaylist(playlistId: number, tracks: Track[]) {
    const r = await api<{ added: number; skipped: number }>(`/playlists/${playlistId}/tracks`, { method: 'POST', body: { track_ids: tracks.map((t) => t.id) } })
    await loadPlaylists()
    return r
  }

  function reset() {
    favoriteOverrides.clear()
    ratingOverrides.clear()
    playlists.value = []
    sharedPlaylists.value = []
    videoPlaylists.value = []
  }

  return { isFavorite, toggleFavorite, rating, rate, playlists, sharedPlaylists, loadPlaylists, videoPlaylists, loadVideoPlaylists, createPlaylist, addToPlaylist, reset }
})
