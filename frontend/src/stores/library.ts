import { defineStore } from 'pinia'
import { reactive, ref } from 'vue'
import { api } from '../api'
import type { Playlist, Track } from '../types'

/** Shared per-user state used across views: likes and stars set here (overriding what lists
 * loaded earlier say) and the playlist list. */
export const useLibrary = defineStore('library', () => {
  // track lists come from many endpoints; local toggles override their is_favorite flag
  const favoriteOverrides = reactive(new Map<number, boolean>())
  const ratingOverrides = reactive(new Map<number, number | null>())
  const playlists = ref<Playlist[]>([])

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
    playlists.value = (await api<{ items: Playlist[] }>('/playlists')).items
  }

  async function createPlaylist(name: string) {
    const p = await api<Playlist>('/playlists', { method: 'POST', body: { name } })
    await loadPlaylists()
    return p
  }

  async function addToPlaylist(playlistId: number, tracks: Track[]) {
    await api(`/playlists/${playlistId}/tracks`, { method: 'POST', body: { track_ids: tracks.map((t) => t.id) } })
    await loadPlaylists()
  }

  function reset() {
    favoriteOverrides.clear()
    ratingOverrides.clear()
    playlists.value = []
  }

  return { isFavorite, toggleFavorite, rating, rate, playlists, loadPlaylists, createPlaylist, addToPlaylist, reset }
})
