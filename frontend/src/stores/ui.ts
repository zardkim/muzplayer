import { defineStore } from 'pinia'
import { onScopeDispose, ref, watch } from 'vue'
import type { Track } from '../types'

const PREFS_KEY = 'muz.ui'

// remembered per browser; storage may be blocked (private window), then it just isn't kept
function loadPrefs(): { barHidden?: boolean; sidebarCollapsed?: boolean; views?: Record<string, string> } {
  try {
    return JSON.parse(localStorage.getItem(PREFS_KEY) || '{}')
  } catch {
    return {}
  }
}

export const useUi = defineStore('ui', () => {
  const toast = ref<{ text: string; error: boolean } | null>(null)
  let timer: number | undefined
  function notify(text: string, error = false) {
    toast.value = { text, error }
    clearTimeout(timer)
    timer = window.setTimeout(() => (toast.value = null), 3200)
  }

  const playerOpen = ref(false) // full-screen player (phone layout, or the PC player)
  const queueOpen = ref(false) // queue panel
  const playlistPicker = ref<Track[] | null>(null) // tracks waiting to be added to a playlist
  const lyricsOpen = ref(false) // full player shows lyrics instead of the artwork
  // when App.vue last asked whether the library changed; 0 makes the next page change ask
  // (after this person changed it, e.g. applied a banner, the kept lists must not wait a minute)
  const libraryCheckedAt = ref(0)
  // the video sheet (App.vue): an album's or a song's videos
  const videoTarget = ref<{ albumId?: number; trackId?: number; title: string; artist: string } | null>(null)

  // PC: the bottom player bar can be tucked away, the sidebar folded to icons, and each list page
  // shown as a list, covers or a grid
  const prefs = loadPrefs()
  const barHidden = ref(!!prefs.barHidden)
  const sidebarCollapsed = ref(!!prefs.sidebarCollapsed)
  const views = ref<Record<string, string>>(prefs.views ?? {})
  watch(
    [barHidden, sidebarCollapsed, views],
    () => {
      try {
        localStorage.setItem(PREFS_KEY, JSON.stringify({ barHidden: barHidden.value, sidebarCollapsed: sidebarCollapsed.value, views: views.value }))
      } catch {
        /* not kept */
      }
    },
    { deep: true },
  )

  // PC layout (sidebar, bottom bar, PC player): the md breakpoint, as in App.vue's classes
  const wide = ref(globalThis.matchMedia?.('(min-width: 768px)').matches ?? true)
  const mq = globalThis.matchMedia?.('(min-width: 768px)')
  const onChange = (e: MediaQueryListEvent) => (wide.value = e.matches)
  mq?.addEventListener('change', onChange)
  onScopeDispose(() => mq?.removeEventListener('change', onChange))

  // which side of the PC player is shown: lyrics or the queue
  const playerTab = ref<'lyrics' | 'queue'>('lyrics')

  return {
    toast, notify, playerOpen, queueOpen, playlistPicker, lyricsOpen, libraryCheckedAt, videoTarget,
    barHidden, sidebarCollapsed, views, wide, playerTab,
  }
})
