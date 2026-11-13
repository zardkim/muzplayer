import { defineStore } from 'pinia'
import { computed, ref, watch } from 'vue'
import { api } from '../api'
import type { Lyrics } from '../types'
import { usePlayer } from './player'

// Lyrics of the song that is playing, fetched once per song and shared by the bottom bar's
// one-line lyric, the phone player and the PC player.
export const useLyrics = defineStore('lyrics', () => {
  const player = usePlayer()
  const cache = new Map<number, Lyrics>()
  const fresh = new Map<number, number>() // songs whose lyrics an admin just changed: past the browser's cache
  const lyrics = ref<Lyrics | null>(null)
  const loading = ref(false)

  async function load(id: number | undefined) {
      lyrics.value = id ? (cache.get(id) ?? null) : null
      loading.value = false
      if (!id || cache.has(id)) return
      loading.value = true
      try {
        const data = await api<Lyrics>(`/tracks/${id}/lyrics${fresh.has(id) ? `?v=${fresh.get(id)}` : ''}`)
        if (cache.size > 200) cache.clear()
        // none yet: not kept, so the next play asks again (the server may not have looked them up yet)
        if (data.synced || data.plain) cache.set(id, data)
        if (player.current?.id === id) lyrics.value = data
      } catch {
        /* no lyrics shown; the panel says so */
      } finally {
        if (player.current?.id === id) loading.value = false
      }
  }
  watch(() => (player.mode === 'music' ? player.current?.id : undefined), load, { immediate: true })

  /** After an admin changed a song's lyrics (LyricsAdminSheet): asked again, now if it plays. */
  function reload(id: number) {
    cache.delete(id)
    fresh.set(id, Date.now())
    if (player.mode === 'music' && player.current?.id === id) void load(id)
  }

  // index of the synced line being sung (-1 before the first one or without synced lyrics)
  const activeIndex = computed(() => {
    const synced = lyrics.value?.synced
    if (!synced) return -1
    const now = player.currentTime + 0.2
    let i = -1
    while (i + 1 < synced.length && synced[i + 1][0] <= now) i++
    return i
  })
  // the one-line places (bottom bar, under the title) show a line's first part: a line sung may
  // come with how it is read and its translation under it (backend lyrics.py)
  const line = computed(() => (activeIndex.value >= 0 ? lyrics.value!.synced![activeIndex.value][1].split('\n')[0] : ''))

  return { lyrics, loading, activeIndex, line, reload, fresh }
})
