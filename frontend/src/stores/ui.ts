import { defineStore } from 'pinia'
import { onScopeDispose, ref, watch } from 'vue'
import type { Track } from '../types'

const PREFS_KEY = 'muz.ui'

// remembered per browser; storage may be blocked (private window), then it just isn't kept
export const THEMES = ['default', 'plexamp'] as const
export type Theme = (typeof THEMES)[number]
// the browser's bar colour per theme (meta theme-color)
const THEME_BARS: Record<Theme, string> = { default: '#FFFFFF', plexamp: '#CBC5BF' }

// display and player options from Settings, kept per browser
export interface PlayerPrefs {
  openOnPlay: boolean // starting a list opens the player
  keepAwake: boolean // the screen stays on while the player is open
  musicSpeed: boolean // a speed control for music too (audiobooks always have one)
  showYear: boolean // album year on the player and in album lists
  showVolume: boolean // volume slider on the PC bar
  prefetchWifi: number // songs fetched ahead of time on Wi-Fi (and on iPhone, which doesn't say)
  prefetchCellular: number // ... on mobile data (Android)
  cacheMB: number // the most fetched songs kept on this device
  autoplay: boolean // when the queue runs out, play on with songs like the last one
  albumEnd: 'radio' | 'artist' | 'stop' // with autoplay, after a whole album
  showCodec: boolean // codec and quality (FLAC 24/96) on the player
  showQuality: boolean // Hi-Res / Lossless badge on albums
  showPopular: boolean // mark an album's most played songs
  leveling: 'off' | 'track' | 'album' // ReplayGain volume levelling
  crossfade: number // seconds songs overlap (0 = off)
  eq: boolean // equaliser on
  eqPreset: string // a key of EQ_PRESETS, or 'custom'
  eqGains: number[] // dB per band (custom)
}
export const CROSSFADES = [0, 2, 4, 6, 8]
export const PREFETCH_COUNTS = [0, 1, 2, 3, 5]
export const CACHE_SIZES = [256, 512, 1024, 2048]
const PLAYER_PREFS: PlayerPrefs = {
  openOnPlay: false, keepAwake: false, musicSpeed: false, showYear: true, showVolume: true,
  prefetchWifi: 3, prefetchCellular: 1, cacheMB: 512, autoplay: false, albumEnd: 'radio',
  showCodec: true, showQuality: true, showPopular: true,
  leveling: 'off', crossfade: 0, eq: false, eqPreset: 'flat', eqGains: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
}

function loadPrefs(): { barHidden?: boolean; sidebarCollapsed?: boolean; views?: Record<string, string>; theme?: string; player?: Partial<PlayerPrefs> } {
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
  // colour theme; index.html applies the stored one before the first paint, this keeps it in step
  const playerPrefs = ref<PlayerPrefs>({ ...PLAYER_PREFS, ...prefs.player })
  const theme = ref<Theme>((THEMES as readonly string[]).includes(prefs.theme ?? '') ? (prefs.theme as Theme) : 'default')
  watch(
    theme,
    (v) => {
      const root = document.documentElement
      if (v === 'default') delete root.dataset.theme
      else root.dataset.theme = v
      document.querySelector('meta[name="theme-color"]')?.setAttribute('content', THEME_BARS[v])
    },
    { immediate: true },
  )
  watch(
    [barHidden, sidebarCollapsed, views, theme, playerPrefs],
    () => {
      try {
        localStorage.setItem(PREFS_KEY, JSON.stringify({ barHidden: barHidden.value, sidebarCollapsed: sidebarCollapsed.value, views: views.value, theme: theme.value, player: playerPrefs.value }))
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
    barHidden, sidebarCollapsed, views, theme, playerPrefs, wide, playerTab,
  }
})
