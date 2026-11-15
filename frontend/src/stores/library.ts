import { defineStore } from 'pinia'
import { computed, reactive, ref } from 'vue'
import { api } from '../api'
import type { Playlist, Track, VideoPlaylist } from '../types'
import { useUi } from './ui'

/** Shared per-user state used across views: likes and stars set here (overriding what lists
 * loaded earlier say) and the playlist list. */
export const useLibrary = defineStore('library', () => {
  // track lists come from many endpoints; local toggles override their is_favorite flag
  const favoriteOverrides = reactive(new Map<number, boolean>())
  const ratingOverrides = reactive(new Map<number, number | null>())
  const ui = useUi()
  const mine = ref<Playlist[]>([])
  // my playlists in the order picked on the playlists page (kept with the account): lately changed
  // (the server's order) or by name, the default one first, or in my own order (lists not placed yet first)
  const playlists = computed(() => {
    const how = ui.views.playlistSort
    if (how === 'name') return [...mine.value].sort((a, b) => Number(!!b.is_default) - Number(!!a.is_default) || a.name.localeCompare(b.name, 'ko'))
    if (how === 'manual') return [...mine.value].sort((a, b) => (a.sort_order ?? -1) - (b.sort_order ?? -1))
    return mine.value
  })
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
    const [own, shared] = await Promise.all([
      api<{ items: Playlist[] }>('/playlists'),
      api<{ items: Playlist[] }>('/playlists/shared').catch(() => ({ items: sharedPlaylists.value })),
    ])
    mine.value = own.items
    sharedPlaylists.value = shared.items
  }

  /** Lists songs can be put into: my own (not smart) and the shared ones I may change. */
  const editablePlaylists = computed(() => [...playlists.value.filter((p) => p.kind !== 'smart'), ...sharedPlaylists.value.filter((p) => p.can_edit)])

  /** My own order: these lists (all of mine) top to bottom. */
  async function orderPlaylists(ids: number[]) {
    mine.value = mine.value.map((p) => ({ ...p, sort_order: ids.indexOf(p.id) }))
    await api('/playlists/order', { method: 'PUT', body: { playlist_ids: ids } })
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
    mine.value = []
    sharedPlaylists.value = []
    videoPlaylists.value = []
  }

  return { isFavorite, toggleFavorite, rating, rate, playlists, sharedPlaylists, editablePlaylists, orderPlaylists, loadPlaylists, videoPlaylists, loadVideoPlaylists, createPlaylist, addToPlaylist, reset }
})
