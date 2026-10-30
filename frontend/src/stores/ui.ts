import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { Track } from '../types'

export const useUi = defineStore('ui', () => {
  const toast = ref<{ text: string; error: boolean } | null>(null)
  let timer: number | undefined
  function notify(text: string, error = false) {
    toast.value = { text, error }
    clearTimeout(timer)
    timer = window.setTimeout(() => (toast.value = null), 3200)
  }

  const playerOpen = ref(false) // full-screen player (mobile)
  const queueOpen = ref(false) // queue panel
  const playlistPicker = ref<Track[] | null>(null) // tracks waiting to be added to a playlist
  const lyricsOpen = ref(false) // full player shows lyrics instead of the artwork
  // when App.vue last asked whether the library changed; 0 makes the next page change ask
  // (after this person changed it, e.g. applied a banner, the kept lists must not wait a minute)
  const libraryCheckedAt = ref(0)
  // the video sheet (App.vue): an album's or a song's videos
  const videoTarget = ref<{ albumId?: number; trackId?: number; title: string; artist: string } | null>(null)

  return { toast, notify, playerOpen, queueOpen, playlistPicker, lyricsOpen, libraryCheckedAt, videoTarget }
})
