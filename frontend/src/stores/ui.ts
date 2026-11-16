import { defineStore } from 'pinia'
import { onScopeDispose, ref, watch } from 'vue'
import type { Track } from '../types'
import type { Quality } from '../stream'

const PREFS_KEY = 'muz.ui'

// remembered per browser; storage may be blocked (private window), then it just isn't kept
export const THEMES = ['default', 'plexamp', 'spotify', 'melon'] as const
export type Theme = (typeof THEMES)[number]
// the browser's bar colour per theme (meta theme-color)
const THEME_BARS: Record<Theme, string> = { default: '#FFFFFF', plexamp: '#CBC5BF', spotify: '#121212', melon: '#FFFFFF' }
// the home screen icon (index.html muzAppIcon; public/icon-<name>-*.png, manifest-<name>.webmanifest)
export const APP_ICONS = ['auto', 'light', 'dark', 'pink', 'navy'] as const
export type AppIcon = (typeof APP_ICONS)[number]

// display and player options from Settings, kept per browser
export interface PlayerPrefs {
  openOnPlay: boolean // starting a list opens the player
  startMinimized: boolean // the app starts with the mini player tucked away (it comes back on play)
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
  quality: Quality // streaming quality on Wi-Fi (and on iPhone, which doesn't say); needs ffmpeg on the server
  qualityCellular: Quality // ... on mobile data (Android)
  lyricsSize: number // index into LYRICS_SIZES
}
export const CROSSFADES = [0, 2, 4, 6, 8]
export const LYRICS_SIZES = [0.8, 0.9, 1, 1.15, 1.3, 1.5, 1.75] // times the lyrics' normal size
// settings that fit one device only: not sent to the account (prefsSync.ts)
export const PLAYER_PREFS_DEVICE: (keyof PlayerPrefs)[] = ['prefetchWifi', 'prefetchCellular', 'cacheMB']
export const PREFETCH_COUNTS = [0, 1, 2, 3, 5]
export const CACHE_SIZES = [256, 512, 1024, 2048]
const PLAYER_PREFS: PlayerPrefs = {
  openOnPlay: false, startMinimized: false, keepAwake: false, musicSpeed: false, showYear: true, showVolume: true,
  prefetchWifi: 3, prefetchCellular: 1, cacheMB: 512, autoplay: false, albumEnd: 'radio',
  showCodec: true, showQuality: true, showPopular: true,
  leveling: 'off', crossfade: 0, eq: false, eqPreset: 'flat', eqGains: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
  quality: 'orig', qualityCellular: 'orig', lyricsSize: 2,
}

function loadPrefs(): { barHidden?: boolean; sidebarCollapsed?: boolean; views?: Record<string, string>; theme?: string; appIcon?: string; player?: Partial<PlayerPrefs>; radio?: RadioMarks } {
  try {
    return JSON.parse(localStorage.getItem(PREFS_KEY) || '{}')
  } catch {
    return {}
  }
}

// radio stations (ids): the ones listened to lately (newest first) and the starred ones; kept with the
// account, so every device shows the same (prefsSync.ts)
// hidden: left out of the Radio page's lists; tunerNoise: the tuner's hiss between stations (this device);
// presets: the tuner's memory buttons 1–6, a station id or null each, by region and band
export interface RadioMarks {
  recent: string[]
  favorites: string[]
  hidden?: string[]
  tunerNoise?: boolean
  presets?: Record<string, Partial<Record<'FM' | 'AM' | 'NET', (string | null)[]>>>
}
export const RADIO_RECENT_KEPT = 12

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
  // the video sheet (App.vue): an album's or a song's videos; play: start one at once (a video id, or the first)
  const videoTarget = ref<{ albumId?: number; trackId?: number; title: string; artist: string; play?: number | 'first' } | null>(null)
  // a song's videos changed in the video sheet: lists showing it update their YouTube mark
  const videoChanged = ref<{ trackId: number; has: boolean } | null>(null)
  // the video player (App.vue): videos one after another (or shuffled), from start
  const videoQueue = ref<{ items: import('../types').VideoListItem[]; start: number; shuffle?: boolean; title?: string } | null>(null)
  // a NAS video's thumbnail made again: its new address (the browser keeps the old one a day)
  const thumbBust = ref<Record<number, number>>({})
  const inlineVideo = ref<number | null>(null) // the video card playing in place (InlineVideo.vue)
  // a video whose song or album is being picked (App.vue: search by a keyword, pick one)
  const videoLink = ref<import('../types').VideoListItem | null>(null)
  const videoLinkTab = ref<'track' | 'album'>('track')
  // a video's song changed there: lists showing it load again
  const videoLinked = ref(0)
  // videos to put in a video playlist (the picker, App.vue)
  const videoPick = ref<import('../types').VideoListItem[] | null>(null)
  // the lyrics sheet (App.vue): a song's lyrics from a list, without playing it
  const lyricsTarget = ref<{ trackId: number; title: string; artist: string } | null>(null)
  // admins: a song's lyrics to fix (LyricsAdminSheet)
  const lyricsAdmin = ref<{ trackId: number; title: string; artist: string } | null>(null)

  // PC: the bottom player bar can be tucked away, the sidebar folded to icons, and each list page
  // shown as a list, covers or a grid
  const prefs = loadPrefs()
  const barHidden = ref(!!prefs.barHidden || !!prefs.player?.startMinimized) // Settings → start minimized
  const sidebarCollapsed = ref(!!prefs.sidebarCollapsed)
  const views = ref<Record<string, string>>(prefs.views ?? {})
  // colour theme; index.html applies the stored one before the first paint, this keeps it in step
  const playerPrefs = ref<PlayerPrefs>({ ...PLAYER_PREFS, ...prefs.player })
  const radio = ref<RadioMarks>({ ...prefs.radio, recent: prefs.radio?.recent ?? [], favorites: prefs.radio?.favorites ?? [], hidden: prefs.radio?.hidden ?? [] })
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
  // the home screen icon; index.html set the stored one up before this ran
  const appIcon = ref<AppIcon>((APP_ICONS as readonly string[]).includes(prefs.appIcon ?? '') ? (prefs.appIcon as AppIcon) : 'auto')
  // and a cookie, so the server writes it into the page (backend main.py index_html): iPhone takes the
  // icon from the links the page came with
  watch(
    appIcon,
    (v) => {
      ;(window as unknown as { muzAppIcon?: (v: string) => void }).muzAppIcon?.(v)
      document.cookie = v === 'auto' ? 'muz_icon=; path=/; max-age=0' : `muz_icon=${v}; path=/; max-age=31536000; SameSite=Lax`
    },
    { immediate: true },
  )
  watch(
    [barHidden, sidebarCollapsed, views, theme, appIcon, playerPrefs, radio],
    () => {
      try {
        localStorage.setItem(PREFS_KEY, JSON.stringify({ barHidden: barHidden.value, sidebarCollapsed: sidebarCollapsed.value, views: views.value, theme: theme.value, appIcon: appIcon.value, player: playerPrefs.value, radio: radio.value }))
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
    radio, toast, notify, playerOpen, queueOpen, playlistPicker, lyricsOpen, libraryCheckedAt, videoTarget, lyricsTarget, lyricsAdmin, videoChanged, videoQueue, videoPick, thumbBust, inlineVideo, videoLink, videoLinkTab, videoLinked,
    barHidden, sidebarCollapsed, views, theme, appIcon, playerPrefs, wide, playerTab,
  }
})
