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
  const lyrics = ref<Lyrics | null>(null)
  const loading = ref(false)

  watch(
    () => (player.mode === 'music' ? player.current?.id : undefined),
    async (id) => {
      lyrics.value = id ? (cache.get(id) ?? null) : null
      loading.value = false
      if (!id || cache.has(id)) return
      loading.value = true
      try {
        const data = await api<Lyrics>(`/tracks/${id}/lyrics`)
        if (cache.size > 200) cache.clear()
        // none yet: not kept, so the next play asks again (the server may not have looked them up yet)
        if (data.synced || data.plain) cache.set(id, data)
        if (player.current?.id === id) lyrics.value = data
      } catch {
        /* no lyrics shown; the panel says so */
      } finally {
        if (player.current?.id === id) loading.value = false
      }
    },
    { immediate: true },
  )

  // index of the synced line being sung (-1 before the first one or without synced lyrics)
  const activeIndex = computed(() => {
    const synced = lyrics.value?.synced
    if (!synced) return -1
    const now = player.currentTime + 0.2
    let i = -1
    while (i + 1 < synced.length && synced[i + 1][0] <= now) i++
    return i
  })
  const line = computed(() => (activeIndex.value >= 0 ? lyrics.value!.synced![activeIndex.value][1] : ''))

  return { lyrics, loading, activeIndex, line }
})
