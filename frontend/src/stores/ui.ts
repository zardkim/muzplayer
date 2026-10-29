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

  return { toast, notify, playerOpen, queueOpen, playlistPicker }
})
