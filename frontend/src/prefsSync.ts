import { watch } from 'vue'
import { i18n, LOCALES, setLocale, type Locale } from './i18n'
import { useAuth } from './stores/auth'
import { usePlayer } from './stores/player'
import { PLAYER_PREFS_DEVICE, THEMES, useUi, type PlayerPrefs, type Theme } from './stores/ui'

// The settings page's choices, kept with the account on the server, so every device, app and address
// (the NAS's own address at home, the domain outside, the Windows app) has the same ones. Each
// device keeps its own copy too (it starts with it, and works offline). Every change is stamped:
// on starting, the newer of this device's and the server's wins (a change made just before the app
// was closed, not sent yet, isn't undone by the older one on the server). A change is sent at
// once, and anything still waiting when the app is closed or hidden goes then. What only fits one
// device stays on it (PLAYER_PREFS_DEVICE: prefetching and the cache size), as do the layout and the volume.
type Prefs = {
  v: 1
  t: number // when changed (ms)
  theme: Theme
  locale: Locale
  player: Partial<PlayerPrefs>
  skipBack: number
  skipForward: number
}

export function startPrefsSync() {
  const auth = useAuth()
  const ui = useUi()
  const player = usePlayer()
  let applying = false
  let timer: number | undefined
  let syncedFor: number | null = null
  let pending = false
  const stampKey = (id: number) => `muz.prefs.t.${id}`
  function stamp(id: number): number {
    try {
      return Number(localStorage.getItem(stampKey(id))) || 0
    } catch {
      return 0
    }
  }
  function setStamp(id: number, t: number) {
    try {
      localStorage.setItem(stampKey(id), String(t))
    } catch {
      /* storage unavailable: the server's then win */
    }
  }

  function collect(): Omit<Prefs, 't'> {
    const p: Partial<PlayerPrefs> = { ...ui.playerPrefs }
    for (const k of PLAYER_PREFS_DEVICE) delete p[k]
    return {
      v: 1,
      theme: ui.theme,
      locale: i18n.global.locale.value as Locale,
      player: p,
      skipBack: player.skipBack,
      skipForward: player.skipForward,
    }
  }

  function apply(s: Partial<Prefs>) {
    applying = true
    try {
      if (s.theme && (THEMES as readonly string[]).includes(s.theme)) ui.theme = s.theme
      if (s.locale && LOCALES.some((l) => l.code === s.locale)) setLocale(s.locale)
      if (s.player) {
        const known = Object.fromEntries(
          Object.entries(s.player).filter(([k, v]) => k in ui.playerPrefs && !PLAYER_PREFS_DEVICE.includes(k as keyof PlayerPrefs) && typeof v === typeof ui.playerPrefs[k as keyof PlayerPrefs]),
        )
        ui.playerPrefs = { ...ui.playerPrefs, ...known }
      }
      if (typeof s.skipBack === 'number') player.skipBack = s.skipBack
      if (typeof s.skipForward === 'number') player.skipForward = s.skipForward
    } finally {
      // the watcher below runs after this tick: it must not send back what just arrived
      queueMicrotask(() => (applying = false))
    }
  }

  // signed in (or the page loaded signed in): the account's settings, or this device's sent up first
  watch(
    () => auth.user?.id ?? null,
    (id) => {
      syncedFor = id
      if (id === null) return
      const saved = auth.user?.prefs as Partial<Prefs> | null | undefined
      const mine = stamp(id)
      if (saved && saved.v === 1 && (saved.t ?? 0) >= mine) {
        apply(saved)
        setStamp(id, saved.t ?? 0)
      } else send(mine || Date.now()) // this device's are newer (or the server has none yet)
    },
    { immediate: true },
  )

  function send(t: number) {
    if (syncedFor === null) return
    pending = false
    clearTimeout(timer)
    auth.updateSettings({ prefs: { ...collect(), t } }).catch(() => {
      /* offline: this device's stamp is newer, so they go up on the next start */
    })
  }

  watch(
    collect,
    () => {
      if (applying || syncedFor === null) return
      const t = Date.now()
      setStamp(syncedFor, t)
      pending = true
      clearTimeout(timer)
      timer = window.setTimeout(() => send(t), 250) // a slider or a few quick taps: one request
    },
    { deep: true },
  )

  // closing the app or switching away: what is still waiting goes now (keepalive outlives the page)
  function flush() {
    if (!pending || syncedFor === null) return
    pending = false
    clearTimeout(timer)
    const body = JSON.stringify({ prefs: { ...collect(), t: stamp(syncedFor) } })
    fetch('/api/v1/auth/me', { method: 'PATCH', headers: { 'content-type': 'application/json' }, body, keepalive: true, credentials: 'same-origin' }).catch(() => {})
  }
  document.addEventListener('visibilitychange', () => document.visibilityState === 'hidden' && flush())
  window.addEventListener('pagehide', flush)
}
