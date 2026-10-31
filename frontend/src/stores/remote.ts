import { defineStore } from 'pinia'
import { computed, ref, watch } from 'vue'
import { api } from '../api'
import { isIos } from '../pwa'
import type { Track } from '../types'
import { useAuth } from './auth'
import { usePlayer } from './player'

// Remote control between one person's devices (backend api/remote.py): this tab is a device that
// reports what it plays and takes commands; another device can be watched and controlled from the
// devices sheet, and the queue moved between them. Music only.
//
// The event stream is open only while the page is visible or this device is playing: a hidden tab
// that plays nothing has nothing to control, and over plain http a browser allows 6 connections
// to the server, which the songs need. A locked iPhone drops it too, so it can't be controlled then.

export interface RemoteState {
  track: Pick<Track, 'id' | 'title' | 'artist' | 'album_id' | 'has_cover' | 'cover_v' | 'duration'> | null
  playing: boolean
  position: number
  duration: number
  volume: number
  canVolume: boolean // iPhone pages can't change the volume
  blocked: boolean // a remote play needs a tap on that device first
  queueLength: number
}
export interface RemoteDevice {
  id: string
  name: string
  state: RemoteState | null
  state_at: number // server seconds
}

const MAX_TRACKS = 500 // queue moved to another device

// crypto.getRandomValues, not randomUUID: that one exists only over https (the NAS may be opened by IP)
const randomId = () => Array.from(crypto.getRandomValues(new Uint8Array(16)), (b) => b.toString(16).padStart(2, '0')).join('')

function deviceId(): string {
  try {
    const saved = sessionStorage.getItem('muz.device') // per tab: commands reach one tab
    if (saved) return saved
    const id = randomId()
    sessionStorage.setItem('muz.device', id)
    return id
  } catch {
    return randomId()
  }
}

function deviceName(): string {
  const ua = navigator.userAgent
  const os = isIos ? (/iPad/.test(ua) || !/iPhone/.test(ua) ? 'iPad' : 'iPhone') : /Android/.test(ua) ? 'Android' : /Mac/.test(ua) ? 'Mac' : /Windows/.test(ua) ? 'Windows' : 'Linux'
  const browser = /Edg\//.test(ua) ? 'Edge' : /Firefox\//.test(ua) ? 'Firefox' : /Chrome\//.test(ua) && !isIos ? 'Chrome' : 'Safari'
  return `${os} · ${browser}`
}

export const useRemote = defineStore('remote', () => {
  const player = usePlayer()
  const auth = useAuth()
  const id = deviceId()
  const name = deviceName()
  const devices = ref<RemoteDevice[]>([]) // the other devices
  const connected = ref(false)
  const target = ref<string | null>(null) // the device being controlled in the sheet
  let offset = 0 // server clock minus ours, in seconds
  let source: EventSource | null = null
  const visible = ref(document.visibilityState === 'visible')
  document.addEventListener('visibilitychange', () => (visible.value = document.visibilityState === 'visible'))

  const wanted = computed(() => !!auth.user && (visible.value || player.playing))
  watch(wanted, (on) => (on ? connect() : disconnect()), { immediate: true })

  function connect() {
    if (source) return
    source = new EventSource(`/api/v1/remote/events?device=${id}&name=${encodeURIComponent(name)}`)
    source.onopen = () => {
      connected.value = true
      void publish()
    }
    source.onerror = () => {
      connected.value = false
      // it tries again by itself after a network error, but not after an error reply (a 502
      // while the server restarts for an update): then start over a little later
      if (source?.readyState === EventSource.CLOSED) {
        source = null
        window.setTimeout(() => wanted.value && connect(), 8000)
      }
    }
    source.onmessage = (e) => {
      const msg = JSON.parse(e.data)
      if (msg.type === 'devices') {
        offset = msg.now - Date.now() / 1000
        devices.value = (msg.list as RemoteDevice[]).filter((d) => d.id !== id)
        if (target.value && !devices.value.some((d) => d.id === target.value)) target.value = null
      } else if (msg.type === 'command') run(msg.cmd, msg.arg, msg.from)
    }
  }
  function disconnect() {
    source?.close()
    source = null
    connected.value = false
    devices.value = []
  }

  // ---- this device: report what it plays ----
  function state(): RemoteState | null {
    if (player.mode !== 'music') return null
    const t = player.current
    return {
      track: t && { id: t.id, title: t.title, artist: t.artist, album_id: t.album_id, has_cover: t.has_cover, cover_v: t.cover_v, duration: t.duration },
      playing: player.playing,
      position: player.currentTime,
      duration: player.duration,
      volume: player.volume,
      canVolume: !isIos,
      blocked: player.blocked,
      queueLength: player.queue.length,
    }
  }
  let lastSent = 0
  async function publish() {
    if (!connected.value) return
    lastSent = Date.now()
    await api('/remote/state', { method: 'POST', body: { device: id, state: state() } }).catch(() => {})
  }
  // on a change, and now and then while playing (the others move the position on themselves)
  watch(() => [player.current?.id, player.playing, player.volume, player.blocked, player.mode, player.queue.length], () => void publish())
  watch(() => player.currentTime, (t, before) => {
    if (Math.abs(t - before) > 3 || (player.playing && Date.now() - lastSent > 10_000)) void publish()
  })
  // at least every 30 s: the server drops a device it hasn't heard from (a page the phone suspended)
  window.setInterval(() => Date.now() - lastSent > 30_000 && void publish(), 10_000)

  /** A command from another device of this person. */
  function run(cmd: string, arg: unknown, from: string) {
    if (cmd !== 'play_tracks' && player.mode !== 'music') return
    switch (cmd) {
      case 'toggle':
        return player.toggle()
      case 'play':
        return player.playing || player.toggle()
      case 'pause':
        return player.playing && player.toggle()
      case 'next':
        return player.next()
      case 'prev':
        return player.prev()
      case 'seek':
        return typeof arg === 'number' && player.seek(arg)
      case 'volume':
        if (typeof arg === 'number') player.volume = Math.min(1, Math.max(0, arg))
        return
      case 'play_tracks': {
        const a = arg as { tracks?: Track[]; index?: number; position?: number }
        if (Array.isArray(a?.tracks) && a.tracks.length) player.playTracks(a.tracks, a.index ?? 0, { shuffle: false, position: a.position, remote: true })
        return
      }
      case 'handoff': // the sender takes over what plays here
        void sendQueue(from)
    }
  }

  // ---- other devices ----
  const targetDevice = computed(() => devices.value.find((d) => d.id === target.value) ?? null)

  /** Where another device is in its song now: its last report moved on by the time since. */
  function positionOf(d: RemoteDevice): number {
    const s = d.state
    if (!s) return 0
    const moved = s.playing ? Date.now() / 1000 + offset - d.state_at : 0
    return Math.min(s.position + Math.max(0, moved), s.duration || Infinity)
  }

  async function command(to: string, cmd: string, arg?: unknown) {
    await api('/remote/command', { method: 'POST', body: { device: id, to, cmd, arg } })
  }

  /** Moves what plays here to another device: it plays on from the same place, this one stops. */
  async function sendQueue(to: string) {
    if (!player.current) return
    const start = Math.max(0, player.index - 50) // keep a little of what was played, for "previous"
    const tracks = player.queue.slice(start, start + MAX_TRACKS)
    await command(to, 'play_tracks', { tracks, index: player.index - start, position: player.currentTime })
    if (player.playing) player.toggle()
  }

  /** Brings what another device plays here (it sends its queue, see 'handoff'). */
  async function takeOver(from: string) {
    await command(from, 'handoff')
  }

  return { id, name, devices, connected, target, targetDevice, positionOf, command, sendQueue, takeOver }
})
