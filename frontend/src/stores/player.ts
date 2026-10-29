import { defineStore } from 'pinia'
import { computed, ref, watch } from 'vue'
import { api, coverUrl, streamUrl } from '../api'
import { errorMessage, i18n } from '../i18n'
import type { Track } from '../types'
import { useUi } from './ui'

type Repeat = 'off' | 'all' | 'one'

const SETTINGS_KEY = 'muz.player'
const queueKey = (userId: number) => `muz.queue.${userId}`

function load<T>(key: string): T | null {
  try {
    const raw = localStorage.getItem(key)
    return raw ? (JSON.parse(raw) as T) : null
  } catch {
    return null
  }
}

function save(key: string, value: unknown) {
  try {
    localStorage.setItem(key, JSON.stringify(value))
  } catch {
    /* storage full or unavailable: the queue simply won't survive a reload */
  }
}

function shuffled<T>(items: T[]): T[] {
  const a = [...items]
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1))
    ;[a[i], a[j]] = [a[j], a[i]]
  }
  return a
}

export const usePlayer = defineStore('player', () => {
  const audio = new Audio()
  audio.preload = 'auto'

  const queue = ref<Track[]>([])
  const index = ref(-1)
  const playing = ref(false)
  const currentTime = ref(0)
  const duration = ref(0)
  const shuffle = ref(false)
  const repeat = ref<Repeat>('off')
  const volume = ref(1)
  let userId: number | null = null
  let loadedId: number | null = null // track whose src is set on the audio element
  let reported = false // history already recorded for the current play
  let originalOrder: Track[] | null = null // queue order before shuffle

  const current = computed<Track | null>(() => queue.value[index.value] ?? null)

  // ---- persistence (per browser, per user) ----
  function restore(forUserId: number) {
    userId = forUserId
    const settings = load<{ volume: number; shuffle: boolean; repeat: Repeat }>(SETTINGS_KEY)
    if (settings) {
      volume.value = settings.volume ?? 1
      shuffle.value = !!settings.shuffle
      repeat.value = settings.repeat ?? 'off'
    }
    const saved = load<{ queue: Track[]; index: number }>(queueKey(forUserId))
    queue.value = saved?.queue ?? []
    index.value = saved && saved.index < queue.value.length ? saved.index : queue.value.length ? 0 : -1
    currentTime.value = 0
    duration.value = current.value?.duration ?? 0
  }

  function persistQueue() {
    if (userId !== null) save(queueKey(userId), { queue: queue.value, index: index.value })
  }
  watch([queue, index], persistQueue, { deep: true })
  watch([volume, shuffle, repeat], () =>
    save(SETTINGS_KEY, { volume: volume.value, shuffle: shuffle.value, repeat: repeat.value }),
  )
  watch(volume, (v) => (audio.volume = v), { immediate: true })

  function reset() {
    audio.pause()
    audio.removeAttribute('src')
    audio.load()
    loadedId = null
    queue.value = []
    index.value = -1
    playing.value = false
    userId = null
  }

  // ---- playback ----
  async function startCurrent() {
    const track = current.value
    if (!track) return
    if (loadedId !== track.id) {
      audio.src = streamUrl(track.id)
      loadedId = track.id
      reported = false
      currentTime.value = 0
      duration.value = track.duration ?? 0
    }
    updateMediaSession()
    try {
      await audio.play()
    } catch {
      // autoplay blocked or aborted by a newer src; the UI stays paused
    }
  }

  function playTracks(tracks: Track[], startAt = 0, opts: { shuffle?: boolean } = {}) {
    const playable = tracks.filter((t) => !t.missing)
    if (!playable.length) return
    const first = tracks[startAt] && !tracks[startAt].missing ? tracks[startAt] : playable[0]
    if (opts.shuffle !== undefined) shuffle.value = opts.shuffle
    if (shuffle.value) {
      originalOrder = playable
      queue.value = [first, ...shuffled(playable.filter((t) => t !== first))]
      index.value = 0
    } else {
      originalOrder = null
      queue.value = playable
      index.value = playable.indexOf(first)
    }
    loadedId = null
    startCurrent()
  }

  function toggle() {
    if (!current.value) return
    if (audio.paused) startCurrent()
    else audio.pause()
  }

  function jump(i: number) {
    if (i < 0 || i >= queue.value.length) return
    index.value = i
    loadedId = null
    startCurrent()
  }

  function next(auto = false) {
    if (!queue.value.length) return
    if (auto && repeat.value === 'one') {
      audio.currentTime = 0
      startCurrent()
      return
    }
    if (index.value + 1 < queue.value.length) jump(index.value + 1)
    else if (repeat.value === 'all') jump(0)
    else if (auto) {
      playing.value = false
    }
  }

  function prev() {
    if (audio.currentTime > 3 || index.value <= 0) {
      audio.currentTime = 0
      return
    }
    jump(index.value - 1)
  }

  function seek(seconds: number) {
    if (!current.value) return
    if (loadedId !== current.value.id) startCurrent()
    audio.currentTime = seconds
    currentTime.value = seconds
  }

  function toggleShuffle() {
    shuffle.value = !shuffle.value
    const cur = current.value
    if (!cur) return
    if (shuffle.value) {
      originalOrder = [...queue.value]
      const rest = queue.value.filter((_, i) => i !== index.value)
      queue.value = [cur, ...shuffled(rest)]
      index.value = 0
    } else if (originalOrder) {
      const kept = new Set(queue.value)
      queue.value = originalOrder.filter((t) => kept.has(t))
      index.value = queue.value.indexOf(cur)
      originalOrder = null
    }
  }

  function cycleRepeat() {
    repeat.value = repeat.value === 'off' ? 'all' : repeat.value === 'all' ? 'one' : 'off'
  }

  // ---- queue editing ----
  function addToQueue(tracks: Track[]) {
    const playable = tracks.filter((t) => !t.missing)
    queue.value.push(...playable)
    originalOrder?.push(...playable)
    if (index.value === -1 && queue.value.length) index.value = 0
  }

  function playNext(tracks: Track[]) {
    const playable = tracks.filter((t) => !t.missing)
    queue.value.splice(index.value + 1, 0, ...playable)
    if (index.value === -1 && queue.value.length) index.value = 0
  }

  function removeAt(i: number) {
    if (i === index.value) {
      queue.value.splice(i, 1)
      if (!queue.value.length) {
        reset()
        return
      }
      index.value = Math.min(i, queue.value.length - 1)
      loadedId = null
      if (playing.value) startCurrent()
      return
    }
    queue.value.splice(i, 1)
    if (i < index.value) index.value--
  }

  function move(from: number, to: number) {
    if (to < 0 || to >= queue.value.length) return
    const [t] = queue.value.splice(from, 1)
    queue.value.splice(to, 0, t)
    if (index.value === from) index.value = to
    else if (from < index.value && to >= index.value) index.value--
    else if (from > index.value && to <= index.value) index.value++
  }

  function clearUpcoming() {
    queue.value.splice(index.value + 1)
  }

  // ---- audio events ----
  audio.addEventListener('play', () => (playing.value = true))
  audio.addEventListener('pause', () => (playing.value = false))
  audio.addEventListener('ended', () => next(true))
  audio.addEventListener('loadedmetadata', () => {
    if (isFinite(audio.duration)) duration.value = audio.duration
  })
  audio.addEventListener('timeupdate', () => {
    currentTime.value = audio.currentTime
    // record a play after 30s or half the track, once per play
    const track = current.value
    if (!reported && track && (audio.currentTime >= 30 || (duration.value > 0 && audio.currentTime >= duration.value / 2))) {
      reported = true
      api('/history', { method: 'POST', body: { track_id: track.id } }).catch(() => {})
    }
    if ('mediaSession' in navigator && duration.value > 0 && navigator.mediaSession.setPositionState) {
      try {
        navigator.mediaSession.setPositionState({
          duration: duration.value,
          position: Math.min(audio.currentTime, duration.value),
          playbackRate: audio.playbackRate,
        })
      } catch {
        /* some browsers reject transient values */
      }
    }
  })
  audio.addEventListener('error', () => {
    if (!audio.getAttribute('src')) return
    useUi().notify(errorMessage({ code: 'playback' }), true)
    if (index.value + 1 < queue.value.length) jump(index.value + 1)
  })

  // ---- lock screen / headset controls ----
  function updateMediaSession() {
    const track = current.value
    if (!('mediaSession' in navigator) || !track) return
    const t = i18n.global.t
    navigator.mediaSession.metadata = new MediaMetadata({
      title: track.title,
      artist: track.artist || t('common.unknownArtist'),
      album: track.album,
      artwork:
        track.has_cover && track.album_id
          ? [
              { src: coverUrl(track.album_id, 'thumb'), sizes: '300x300', type: 'image/jpeg' },
              { src: coverUrl(track.album_id, 'large'), sizes: '1000x1000', type: 'image/jpeg' },
            ]
          : [{ src: '/icon-512.png', sizes: '512x512', type: 'image/png' }],
    })
  }

  if ('mediaSession' in navigator) {
    const ms = navigator.mediaSession
    const handlers: [MediaSessionAction, MediaSessionActionHandler][] = [
      ['play', () => startCurrent()],
      ['pause', () => audio.pause()],
      ['previoustrack', () => prev()],
      ['nexttrack', () => next()],
      ['seekto', (d) => d.seekTime != null && seek(d.seekTime)],
    ]
    for (const [action, handler] of handlers) {
      try {
        ms.setActionHandler(action, handler)
      } catch {
        /* unsupported action */
      }
    }
  }

  return {
    queue,
    index,
    current,
    playing,
    currentTime,
    duration,
    shuffle,
    repeat,
    volume,
    restore,
    reset,
    playTracks,
    toggle,
    jump,
    next,
    prev,
    seek,
    toggleShuffle,
    cycleRepeat,
    addToQueue,
    playNext,
    removeAt,
    move,
    clearUpcoming,
  }
})
