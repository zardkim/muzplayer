import { defineStore } from 'pinia'
import { computed, ref, toRaw, watch } from 'vue'
import { api, bookCoverUrl, bookStreamUrl, coverUrl, query } from '../api'
import { cachedSource, prepare } from '../audioCache'
import { crossfade, EQ_PRESETS, ensureGraph, graphActive, primeTail, resumeGraph, setEq, setLevel, stopTail } from '../audioGraph'
import { errorMessage, i18n } from '../i18n'
import { isSaved } from '../offline'
import { attachOutputs } from '../outputs'
import { mayConvert, onCellular, serverLevels, streamBase, trackSrc } from '../stream'
import type { Album, BookDetail, Chapter, Page, RadioStation, Track } from '../types'
import { useUi } from './ui'

type Repeat = 'off' | 'all' | 'one'
type Mode = 'music' | 'book' | 'live' // live: a radio station (radio.py relays it)

const SETTINGS_KEY = 'muz.player'
const queueKey = (userId: number) => `muz.queue.${userId}`
const bookKey = (userId: number) => `muz.book.${userId}` // open book and mode
const pendingKey = (userId: number) => `muz.bookPending.${userId}` // position not yet saved (offline)

export const SPEEDS = [0.75, 1, 1.25, 1.5, 1.75, 2, 2.5]
export const MUSIC_SPEEDS = [0.75, 0.9, 1, 1.1, 1.25, 1.5] // only with Settings → "music speed" on
export const SKIPS = [10, 15, 30, 60]
const SAVE_EVERY_MS = 15_000
const FINISHED_WITHIN = 30 // seconds before the end that count as finished (at most 2% of the book)
const RESUME_REWIND = 2 // seconds replayed when resuming after a pause

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
  // iPhone: a "playback" audio session plays on with the screen locked or the app in the background,
  // ignores the silent switch and moves to Bluetooth when it connects (Safari 17+; without it, a page
  // that also uses Web Audio counts as "ambient" sound, which stops in the background)
  const session = (navigator as Navigator & { audioSession?: { type: string } }).audioSession
  if (session) session.type = 'playback'
  attachOutputs(audio)

  const queue = ref<Track[]>([])
  const index = ref(-1)
  const playing = ref(false)
  const currentTime = ref(0)
  const duration = ref(0)
  const shuffle = ref(false)
  const repeat = ref<Repeat>('off')
  const volume = ref(1)
  // the browser refused to start playing without a tap here (a remote play: remote.ts tells the sender)
  const blocked = ref(false)
  // Safari: AirPlay speakers or TVs nearby (its own picker sends this element's sound there)
  const airplay = ref(false)
  audio.setAttribute('x-webkit-airplay', 'allow')
  if ('WebKitPlaybackTargetAvailabilityEvent' in window) {
    audio.addEventListener('webkitplaybacktargetavailabilitychanged', (e) => {
      airplay.value = (e as Event & { availability: string }).availability === 'available'
    })
  }
  function showAirPlay() {
    ;(audio as HTMLAudioElement & { webkitShowPlaybackTargetPicker?: () => void }).webkitShowPlaybackTargetPicker?.()
  }
  let userId: number | null = null
  // what the audio element holds: "t<track id>" or "b<book id>:<file index>"
  let loadedKey: string | null = null
  let reported = false // history already recorded for the current play
  let originalOrder: Track[] | null = null // queue order before shuffle
  let failures = 0 // playback errors in a row, reset once something plays

  const current = computed<Track | null>(() => queue.value[index.value] ?? null)

  // ---- audiobook state: the music queue stays as it is while a book plays ----
  const mode = ref<Mode>('music')
  const book = ref<BookDetail | null>(null)
  const station = ref<RadioStation | null>(null) // mode 'live'
  const fileIndex = ref(0)
  const bookPos = ref(0) // seconds on the whole-book timeline
  const rate = ref(1)
  const musicRate = ref(1)
  // counts the times a person started a list playing (Settings: open the player when that happens)
  const playStarts = ref(0)
  const skipBack = ref(15)
  const skipForward = ref(30)
  const sleepUntil = ref<number | null>(null) // Date.now() ms to stop at
  const sleepChapter = ref<number | null>(null) // stop when this chapter ends
  let pendingSeek: number | null = null // applied once the new file's metadata is in
  let lastSaved = 0
  let pausedAt = 0
  // server time of the newest position this device knows about (its own save or a fetch);
  // a newer one on the server means another device has listened since
  let knownUpdatedAt = ''

  const chapters = computed<Chapter[]>(() => book.value?.chapters ?? [])
  const chapterIndex = computed(() => {
    const list = chapters.value
    let i = -1
    for (let k = 0; k < list.length && list[k].start <= bookPos.value + 0.05; k++) i = k
    return i
  })
  const chapter = computed<Chapter | null>(() => chapters.value[chapterIndex.value] ?? null)
  // the stretch the seek bar shows: the current chapter, or the whole book without chapters
  const segment = computed(() => {
    const c = chapter.value
    return c ? { start: c.start, end: c.end } : { start: 0, end: book.value?.duration ?? 0 }
  })

  // ---- persistence (per browser, per user) ----
  function restore(forUserId: number) {
    userId = forUserId
    const settings = load<{ volume: number; shuffle: boolean; repeat: Repeat; rate: number; musicRate: number; skipBack: number; skipForward: number }>(SETTINGS_KEY)
    if (settings) {
      volume.value = settings.volume ?? 1
      shuffle.value = !!settings.shuffle
      repeat.value = settings.repeat ?? 'off'
      rate.value = SPEEDS.includes(settings.rate) ? settings.rate : 1
      musicRate.value = MUSIC_SPEEDS.includes(settings.musicRate) ? settings.musicRate : 1
      skipBack.value = SKIPS.includes(settings.skipBack) ? settings.skipBack : 15
      skipForward.value = SKIPS.includes(settings.skipForward) ? settings.skipForward : 30
    }
    const saved = load<{ queue: Track[]; index: number }>(queueKey(forUserId))
    queue.value = saved?.queue ?? []
    index.value = saved && saved.index < queue.value.length ? saved.index : queue.value.length ? 0 : -1
    currentTime.value = 0
    duration.value = current.value?.duration ?? 0
    flushPending()
    // the open book comes back paused at the position the server has
    const savedBook = load<{ id: number; mode: Mode }>(bookKey(forUserId))
    if (savedBook?.mode === 'book') {
      api<BookDetail>(`/books/${savedBook.id}`)
        .then((detail) => {
          if (userId !== forUserId || mode.value === 'book') return
          openBook(detail, startPosition(detail), false)
        })
        .catch(() => {})
    }
  }

  function persistQueue() {
    if (userId !== null) save(queueKey(userId), { queue: queue.value, index: index.value })
  }
  watch([queue, index], persistQueue, { deep: true })
  watch([volume, shuffle, repeat, rate, musicRate, skipBack, skipForward], () =>
    save(SETTINGS_KEY, {
      volume: volume.value,
      shuffle: shuffle.value,
      repeat: repeat.value,
      rate: rate.value,
      musicRate: musicRate.value,
      skipBack: skipBack.value,
      skipForward: skipForward.value,
    }),
  )
  watch([mode, () => book.value?.id], () => {
    // (a radio station isn't brought back after a reload: the music queue is)
    if (userId !== null) save(bookKey(userId), { id: book.value?.id ?? null, mode: mode.value === 'live' ? 'music' : mode.value })
  })
  watch(volume, (v) => (audio.volume = v), { immediate: true })

  function reset() {
    saveProgress(true) // logout: keep the last seconds
    audio.pause()
    audio.removeAttribute('src')
    audio.load()
    loadedKey = null
    queue.value = []
    index.value = -1
    playing.value = false
    mode.value = 'music'
    book.value = null
    station.value = null
    bookPos.value = 0
    knownUpdatedAt = ''
    clearSleep()
    bindMediaSession()
    userId = null
  }

  // ---- playback ----
  async function startCurrent() {
    const track = current.value
    if (!track) return
    if (mode.value === 'book') leaveBook()
    else if (mode.value === 'live') leaveLive()
    if (loadedKey !== `t${track.id}`) {
      // fetched ahead: no wait on the network; saved for offline: sw.js answers from the device
      const src = trackSrc(track)
      audio.src = cachedSource(track.id, src) ?? (isSaved(track.id) ? `${streamBase(track.id)}?saved=1` : src)
      loadedKey = `t${track.id}`
      pendingSeek = null
      reported = false
      currentTime.value = 0
      duration.value = track.duration ?? 0
    }
    soundSetup(track)
    updateMediaSession()
    try {
      await audio.play()
    } catch (e) {
      // autoplay blocked or aborted by a newer src; the UI stays paused
      if ((e as DOMException)?.name === 'NotAllowedError') blocked.value = true
    }
  }

  /** opts.position: start there (seconds); opts.remote: started from another device (remote.ts),
   *  so the player view doesn't open here */
  function playTracks(tracks: Track[], startAt = 0, opts: { shuffle?: boolean; position?: number; remote?: boolean } = {}) {
    const playable = tracks.filter((t) => !t.missing)
    if (!playable.length) return
    const first = tracks[startAt] && !tracks[startAt].missing ? tracks[startAt] : playable[0]
    if (opts.shuffle !== undefined) shuffle.value = opts.shuffle
    if (!opts.remote) playStarts.value++
    radioOn = false
    if (shuffle.value) {
      originalOrder = playable
      queue.value = [first, ...shuffled(playable.filter((t) => t !== first))]
      index.value = 0
    } else {
      originalOrder = null
      queue.value = playable
      index.value = playable.indexOf(first)
    }
    loadedKey = null
    void startCurrent()
    if (opts.position) pendingSeek = opts.position // applied once the song's metadata is in
  }

  // ---- sound: levelling, equaliser, crossfade (audioGraph.ts; Settings → sound) ----
  const soundPrefs = () => useUi().playerPrefs
  // on iPhone the server levels (stream.ts), so levelling alone doesn't need Web Audio there
  const soundOn = () => {
    const p = soundPrefs()
    return (p.leveling !== 'off' && !serverLevels()) || p.crossfade > 0 || p.eq
  }

  /** The ReplayGain to apply, in dB: track or album gain per Settings, never pushing the peak
   *  past full scale; 0 for untagged songs. */
  function levelFor(track: Track): number {
    const mode = soundPrefs().leveling
    if (mode === 'off' || !track.rg || serverLevels()) return 0
    const [tg, tp, ag, ap] = track.rg
    const [gain, peak] = mode === 'album' && ag != null ? [ag, ap] : tg != null ? [tg, tp] : [ag, ap]
    if (gain == null) return 0
    return peak ? Math.min(gain, -20 * Math.log10(peak)) : gain
  }

  /** Before a song plays (inside the tap): build the graph when a sound feature is on, wake it up. */
  function soundSetup(track: Track) {
    if (!soundOn() && !graphActive()) return
    if (!graphActive()) {
      if (!ensureGraph(audio)) return soundFailed()
      applyEq()
    }
    resumeGraph()
    setLevel(levelFor(track))
  }

  let failedShown = false
  function soundFailed() {
    if (!failedShown) useUi().notify(i18n.global.t('settings.soundFailed'), true)
    failedShown = true
  }

  function applyEq() {
    if (!graphActive()) return
    const p = soundPrefs()
    setEq(p.eq ? (p.eqPreset === 'custom' ? p.eqGains : (EQ_PRESETS[p.eqPreset] ?? EQ_PRESETS.flat)) : EQ_PRESETS.flat)
  }
  // turned on from Settings (a tap): build the graph now so the change is heard at once
  watch(() => [soundOn(), soundPrefs().eq, soundPrefs().eqPreset, [...(soundPrefs().eqGains ?? [])], soundPrefs().leveling], () => {
    if (soundOn()) {
      if (!ensureGraph(audio)) return soundFailed()
      resumeGraph()
    }
    applyEq() // also turns the EQ flat when it was switched off
    if (current.value && mode.value === 'music') setLevel(levelFor(current.value))
  })

  let fadedFrom: number | null = null // the song a crossfade started on (once per song)
  let fadingOut: number | null = null // the outgoing song while the tail plays it (its URL is kept)
  let primed: number | null = null

  /** Near the end of a song: start the next one under the fading end of this one. */
  function checkCrossfade() {
    const secs = soundPrefs().crossfade
    const track = current.value
    if (!secs || !graphActive() || !track || !playing.value || repeat.value === 'one') return
    const hasNext = index.value + 1 < queue.value.length || repeat.value === 'all'
    const left = audio.duration - audio.currentTime
    if (!hasNext || !isFinite(left) || audio.duration < secs * 3 || fadedFrom === track.id) return
    if (left <= secs + 1.5 && primed !== track.id) {
      primed = track.id
      primeTail(audio.currentSrc, audio.currentTime)
    }
    if (left <= secs) {
      fadedFrom = track.id
      fadingOut = track.id
      const src = audio.currentSrc
      const at = audio.currentTime
      const outgoing = levelFor(track)
      next(true)
      crossfade(src, at, secs, outgoing)
      window.setTimeout(() => {
        if (fadingOut === track.id) fadingOut = null
      }, (secs + 1) * 1000)
    }
  }

  // ---- looking ahead: fetch the next songs, and keep the queue from running out ----
  let radioOn = false // started as a radio: plays on even with autoplay off
  let extending = false

  /** After a song starts: fetch the next few (Settings → storage), and with autoplay or a radio,
   *  add more songs while the last one plays (not after it ends: iOS may not let a locked phone
   *  start a song that had to wait for the network). */
  function lookAhead() {
    if (mode.value !== 'music' || !current.value) return
    const prefs = useUi().playerPrefs
    const n = onCellular() ? prefs.prefetchCellular : prefs.prefetchWifi
    const upcoming: { id: number; src: string }[] = []
    for (let k = 1; k <= n && k < queue.value.length; k++) {
      const i = index.value + k
      const t = i < queue.value.length ? queue.value[i] : repeat.value === 'all' ? queue.value[i - queue.value.length] : null
      if (t) upcoming.push({ id: t.id, src: trackSrc(t) })
    }
    void prepare(current.value.id, upcoming, prefs.cacheMB * 1024 * 1024, fadingOut)
    if ((prefs.autoplay || radioOn) && repeat.value === 'off' && index.value === queue.value.length - 1) void extendQueue()
  }

  async function extendQueue() {
    const last = queue.value[queue.value.length - 1]
    if (extending || !last) return
    extending = true
    try {
      const more = await continuation(last)
      // only if nothing changed the queue meanwhile
      if (more.length && queue.value[queue.value.length - 1]?.id === last.id) {
        queue.value.push(...more)
        lookAhead()
      }
    } catch {
      /* offline: the queue just ends */
    } finally {
      extending = false
    }
  }

  /** What follows the last song: after a whole album, per Settings (the artist's next album, a
   *  radio, or nothing); otherwise songs like the last one. */
  async function continuation(last: Track): Promise<Track[]> {
    const albumEnd = useUi().playerPrefs.albumEnd
    const wholeAlbum = !radioOn && last.album_id && last.album_kind !== 'chart' && queue.value.every((t) => t.album_id === last.album_id)
    if (wholeAlbum && albumEnd === 'stop') return []
    if (wholeAlbum && albumEnd === 'artist') {
      const next = await nextAlbum(last.album_id!)
      if (next.length) return next
    }
    const exclude = queue.value.slice(-300).map((t) => t.id).join(',')
    const r = await api<{ tracks: Track[] }>(`/radio${query({ track_id: last.id, exclude, limit: 20 })}`)
    return r.tracks.filter((t) => !t.missing)
  }

  /** The album artist's next album by year after this one, or [] when it was the last. */
  async function nextAlbum(albumId: number): Promise<Track[]> {
    const album = await api<{ artist_id: number | null }>(`/albums/${albumId}`)
    if (!album.artist_id) return []
    const list = await api<Page<Album>>(`/albums${query({ artist_id: album.artist_id, sort: 'year', limit: 500 })}`)
    // oldest first; undated albums last, ties by title
    const oldestFirst = [...list.items].sort((a, b) => (a.year ?? 9999) - (b.year ?? 9999) || a.title.localeCompare(b.title))
    const after = oldestFirst[oldestFirst.findIndex((a) => a.id === albumId) + 1]
    if (!after) return []
    const detail = await api<{ tracks: Track[] }>(`/albums/${after.id}`)
    return detail.tracks.filter((t) => !t.missing)
  }

  /** A radio from one song: it plays at once (still inside the tap, for iOS), the rest follows. */
  function startRadio(track: Track) {
    playTracks([track], 0, { shuffle: false })
    radioOn = true
    void extendQueue()
  }

  async function playAlbum(albumId: number) {
    const album = await api<{ tracks: Track[] }>(`/albums/${albumId}`)
    playTracks(album.tracks, 0)
  }

  function toggle() {
    if (mode.value === 'live') {
      if (playing.value) audio.pause()
      else startLive()
      return
    }
    if (mode.value === 'book') {
      if (playing.value) audio.pause()
      else resumeBook()
      return
    }
    if (!current.value) return
    // go by our own state: after a load error the element is stuck with paused === false
    if (playing.value) {
      audio.pause()
      stopTail()
    } else startCurrent()
  }

  function jump(i: number) {
    if (i < 0 || i >= queue.value.length) return
    stopTail() // a crossfade (re)starts after this, when it is one
    index.value = i
    loadedKey = null
    startCurrent()
  }

  function next(auto = false) {
    if (mode.value === 'live') return
    if (mode.value === 'book') return nextChapter()
    if (!queue.value.length) return
    if (auto && repeat.value === 'one') {
      if (converting()) loadedKey = null // can't seek in it: load it again (finished by now)
      else audio.currentTime = 0
      startCurrent()
      return
    }
    if (index.value + 1 < queue.value.length) jump(index.value + 1)
    else if (repeat.value === 'all') jump(0)
    else if (auto) {
      setPlaying(false)
    }
  }

  function prev() {
    if (mode.value === 'live') return
    if (mode.value === 'book') return prevChapter()
    if (audio.currentTime > 3 || index.value <= 0) {
      seek(0)
      return
    }
    jump(index.value - 1)
  }

  function seek(seconds: number) {
    if (mode.value === 'live') return
    if (mode.value === 'book') return seekBook(seconds)
    if (!current.value) return
    if (loadedKey !== `t${current.value.id}`) startCurrent()
    stopTail()
    fadedFrom = null // seeking back before the end may crossfade again
    currentTime.value = seconds
    if (converting()) {
      // the server is still converting it and sends it as it goes, which can't be sought in: ask
      // for the finished file (it waits for the conversion) and go there once it's in
      pendingSeek = seconds
      const src = audio.currentSrc
      audio.src = src + (src.includes('whole=1') ? '' : '&whole=1')
      if (playing.value) void audio.play().catch(() => {})
      return
    }
    audio.currentTime = seconds
  }

  /** The song is a conversion still arriving from the server (no length yet). */
  function converting() {
    return mode.value === 'music' && !isFinite(audio.duration) && mayConvert(audio.currentSrc)
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
      // compare raw objects: the queue hands out reactive proxies of the same tracks
      const kept = new Set(queue.value.map(toRaw))
      queue.value = originalOrder.filter((t) => kept.has(toRaw(t)))
      index.value = queue.value.findIndex((t) => toRaw(t) === toRaw(cur))
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
    if (originalOrder) {
      // keep them when shuffle is turned off again
      const cur = current.value && toRaw(current.value)
      const at = originalOrder.findIndex((t) => toRaw(t) === cur)
      originalOrder.splice(at + 1, 0, ...playable)
    }
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
      loadedKey = null
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

  // ---- audiobooks ----
  function applyRate() {
    const r = mode.value === 'book' ? rate.value : musicRate.value
    // a new src resets playbackRate in some browsers; defaultPlaybackRate carries over
    audio.defaultPlaybackRate = r
    audio.playbackRate = r
    audio.preservesPitch = true
  }
  watch([rate, musicRate], applyRate)

  /** Saved position, or the start for a finished book. */
  function startPosition(detail: BookDetail) {
    const p = detail.progress
    return p && !p.finished ? p.position : 0
  }

  /** File holding a book position and the offset inside it. */
  function fileAt(pos: number): [number, number] {
    const files = book.value?.files ?? []
    let i = files.length - 1
    while (i > 0 && files[i].offset > pos) i--
    const f = files[i]
    return [i, f ? Math.min(Math.max(0, pos - f.offset), f.duration) : 0]
  }

  function loadFile(i: number, local: number, autoplay: boolean) {
    const b = book.value
    if (!b || !b.files[i]) return
    const key = `b${b.id}:${i}`
    fileIndex.value = i
    duration.value = b.files[i].duration
    if (loadedKey !== key) {
      audio.src = bookStreamUrl(b.id, i)
      loadedKey = key
      // Safari ignores currentTime before metadata: apply it on loadedmetadata
      pendingSeek = local
      applyRate()
    } else if (audio.readyState >= 1) {
      audio.currentTime = local
    } else {
      pendingSeek = local
    }
    currentTime.value = local
    bookPos.value = b.files[i].offset + local
    if (autoplay) audio.play().catch(() => {})
  }

  function seekBook(pos: number, autoplay = playing.value) {
    const b = book.value
    if (!b) return
    const [i, local] = fileAt(Math.min(Math.max(0, pos), Math.max(0, b.duration - 0.5)))
    loadFile(i, local, autoplay)
  }

  function openBook(detail: BookDetail, position: number, autoplay: boolean) {
    if (mode.value === 'book' && book.value && book.value.id !== detail.id) saveProgress()
    if (mode.value !== 'book') audio.pause()
    station.value = null
    mode.value = 'book'
    book.value = detail
    knownUpdatedAt = detail.progress?.updated_at ?? ''
    loadedKey = null
    clearSleep()
    applyRate()
    bindMediaSession()
    if (autoplay) seekBook(position, true)
    else {
      // show the position without loading audio until play is pressed
      const [i, local] = fileAt(position)
      fileIndex.value = i
      currentTime.value = local
      duration.value = detail.files[i]?.duration ?? 0
      bookPos.value = position
    }
    updateMediaSession()
  }

  /** Starts a book: at `position`, else where this user left off. */
  function playBook(detail: BookDetail, position?: number) {
    openBook(detail, position ?? startPosition(detail), true)
  }

  function resumeBook() {
    const b = book.value
    if (!b) return
    if (loadedKey === `b${b.id}:${fileIndex.value}`) {
      if (pausedAt && Date.now() - pausedAt > 5000) audio.currentTime = Math.max(0, audio.currentTime - RESUME_REWIND)
      audio.play().catch(() => {})
    } else {
      seekBook(bookPos.value - (pausedAt ? RESUME_REWIND : 0), true)
    }
  }

  // ---- live radio (radio.py relays the station; Radio page) ----
  /** A station, live. Music and books keep their place: playing one of them ends the radio. */
  function playStation(st: RadioStation) {
    if (mode.value === 'book') leaveBook()
    stopTail()
    audio.pause()
    mode.value = 'live'
    station.value = st
    loadedKey = `r${st.id}`
    bindMediaSession()
    updateMediaSession()
    startLive()
  }

  /** (Re)connects: a paused station picks up at "now", not where it stopped. */
  function startLive() {
    const st = station.value
    if (!st) return
    audio.src = `/api/v1/radio/${encodeURIComponent(st.id)}/stream?t=${Date.now()}`
    currentTime.value = 0
    duration.value = 0
    audio.play().catch((e: Error) => {
      if (e?.name === 'NotAllowedError') blocked.value = true
    })
  }

  function stopStation() {
    audio.pause()
    audio.removeAttribute('src')
    audio.load()
    leaveLive()
    setPlaying(false)
    updateMediaSession()
  }

  function leaveLive() {
    station.value = null
    mode.value = 'music'
    loadedKey = null
    bindMediaSession()
  }

  function leaveBook() {
    saveProgress()
    clearSleep()
    mode.value = 'music'
    loadedKey = null
    applyRate()
    bindMediaSession()
  }

  function skip(seconds: number) {
    if (book.value) seekBook(bookPos.value + seconds)
  }

  function jumpChapter(i: number, autoplay = true) {
    const c = chapters.value[i]
    if (c) seekBook(c.start, autoplay)
  }

  function nextChapter() {
    if (chapterIndex.value + 1 < chapters.value.length) jumpChapter(chapterIndex.value + 1, playing.value)
    else skip(skipForward.value)
  }

  function prevChapter() {
    const c = chapter.value
    if (!c) return skip(-skipBack.value)
    // like a CD player: back to the start of this chapter, or the previous one when already there
    if (bookPos.value - c.start > 3 || chapterIndex.value === 0) seekBook(c.start)
    else jumpChapter(chapterIndex.value - 1, playing.value)
  }

  function finished() {
    const b = book.value
    return !!b && b.duration - bookPos.value <= Math.min(FINISHED_WITHIN, b.duration * 0.02)
  }

  function saveProgress(keepalive = false) {
    const b = book.value
    if (!b || userId === null || mode.value !== 'book') return
    const body = { position: Math.round(bookPos.value * 10) / 10, finished: finished() }
    lastSaved = Date.now()
    b.progress = { ...body, updated_at: new Date().toISOString() }
    const forUser = userId
    api<BookDetail['progress']>(`/books/${b.id}/progress`, { method: 'PUT', body, keepalive })
      .then((saved) => {
        if (saved && book.value?.id === b.id) knownUpdatedAt = saved.updated_at
        try {
          localStorage.removeItem(pendingKey(forUser))
        } catch {
          /* storage unavailable */
        }
      })
      // offline: keep it and send it when the app starts again
      .catch(() => save(pendingKey(forUser), { bookId: b.id, ...body, savedAt: new Date().toISOString() }))
  }

  /** Sends a position saved while offline, unless another device has saved a newer one since. */
  async function flushPending() {
    if (userId === null) return
    const p = load<{ bookId: number; position: number; finished: boolean; savedAt?: string }>(pendingKey(userId))
    if (!p) return
    const forUser = userId
    try {
      const server = (await api<BookDetail>(`/books/${p.bookId}`)).progress
      if (!server || !p.savedAt || Date.parse(server.updated_at) < Date.parse(p.savedAt))
        await api(`/books/${p.bookId}/progress`, { method: 'PUT', body: { position: p.position, finished: p.finished } })
      localStorage.removeItem(pendingKey(forUser))
    } catch {
      /* still offline (or the book is gone): try again next start */
    }
  }

  /** Takes over a position saved by another device since this one last saved or looked.
   * Only while paused: never jumps under the listener. */
  function syncBook(detail: BookDetail) {
    const b = book.value
    const p = detail.progress
    if (mode.value !== 'book' || !b || b.id !== detail.id || playing.value || !p) return
    if (knownUpdatedAt && Date.parse(p.updated_at) <= Date.parse(knownUpdatedAt)) return
    knownUpdatedAt = p.updated_at
    b.progress = p
    if (Math.abs(p.position - bookPos.value) > 3) {
      pausedAt = 0 // a fresh position, not a pause to rewind from
      seekBook(p.position, false)
    }
  }

  function refreshBook() {
    const b = book.value
    if (mode.value !== 'book' || !b || playing.value) return
    api<BookDetail>(`/books/${b.id}`)
      .then(syncBook)
      .catch(() => {})
  }

  function clearSleep() {
    sleepUntil.value = null
    sleepChapter.value = null
    audio.volume = volume.value
  }

  /** Minutes, "chapter" (stop when the current chapter ends) or null (off). */
  function setSleep(value: number | 'chapter' | null) {
    clearSleep()
    if (value === 'chapter') sleepChapter.value = Math.max(0, chapterIndex.value)
    else if (value) sleepUntil.value = Date.now() + value * 60_000
  }

  // checked on timeupdate against the wall clock: iOS slows timers in the background
  function checkSleep() {
    if (sleepUntil.value !== null) {
      const left = sleepUntil.value - Date.now()
      if (left <= 0) return sleepNow()
      if (left < 10_000) audio.volume = volume.value * (left / 10_000) // fade out
    }
    if (sleepChapter.value !== null) {
      const c = chapters.value[sleepChapter.value]
      if (!c || chapterIndex.value > sleepChapter.value || bookPos.value >= c.end - 0.3) sleepNow()
    }
  }

  function sleepNow() {
    audio.pause()
    clearSleep()
  }

  function pageHidden() {
    if (mode.value === 'book' && loadedKey) saveProgress(true)
  }
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') return pageHidden()
    refreshBook()
    if (playing.value) resumeGraph() // iPhone may have suspended the sound processing meanwhile
  })
  window.addEventListener('pagehide', pageHidden)

  // ---- audio events ----
  function setPlaying(value: boolean) {
    playing.value = value
    if ('mediaSession' in navigator) navigator.mediaSession.playbackState = value ? 'playing' : 'paused'
  }
  audio.addEventListener('play', () => setPlaying(true))
  // songs added while playing (or a longer queue) are fetched ahead too
  watch(() => queue.value.length, () => {
    if (playing.value) lookAhead()
  })
  audio.addEventListener('playing', () => {
    failures = 0
    blocked.value = false
    lookAhead()
  })
  audio.addEventListener('pause', () => {
    setPlaying(false)
    if (mode.value === 'book' && loadedKey) {
      pausedAt = Date.now()
      saveProgress()
    }
  })
  audio.addEventListener('ended', () => {
    if (mode.value === 'live') return setPlaying(false) // the station's stream ended
    if (mode.value !== 'book') return next(true)
    const b = book.value
    if (b && fileIndex.value + 1 < b.files.length) {
      loadFile(fileIndex.value + 1, 0, true) // next file of the same book
      return
    }
    bookPos.value = b?.duration ?? bookPos.value
    saveProgress()
    clearSleep()
    setPlaying(false)
  })
  audio.addEventListener('loadedmetadata', () => {
    if (isFinite(audio.duration)) duration.value = audio.duration
    if (pendingSeek !== null) {
      audio.currentTime = pendingSeek
      pendingSeek = null
    }
    if (mode.value === 'book') applyRate()
  })
  audio.addEventListener('timeupdate', () => {
    if (mode.value === 'music' && pendingSeek !== null) return // the position of a reload for a seek
    currentTime.value = audio.currentTime
    if (mode.value === 'live') return // listening time only: no history, crossfade or position
    if (mode.value === 'book') {
      if (pendingSeek !== null) return // still the old position of a file being swapped in
      const f = book.value?.files[fileIndex.value]
      if (f) bookPos.value = f.offset + audio.currentTime
      setPosition()
      if (Date.now() - lastSaved > SAVE_EVERY_MS && playing.value) saveProgress()
      checkSleep()
      return
    }
    checkCrossfade()
    // record a play after 30s or half the track, once per play
    const track = current.value
    if (!reported && track && (audio.currentTime >= 30 || (duration.value > 0 && audio.currentTime >= duration.value / 2))) {
      reported = true
      api('/history', { method: 'POST', body: { track_id: track.id } }).catch(() => {})
    }
    setPosition()
  })

  // lock screen position: of the current file, so its slider never crosses into another file
  function setPosition() {
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
  }
  audio.addEventListener('error', () => {
    if (!audio.getAttribute('src')) return
    if (mode.value === 'live') {
      useUi().notify(i18n.global.t('radio.failed'), true)
      audio.pause()
      return
    }
    if (mode.value === 'book') {
      // no "next track" for a book: stop and retry this file on the next play
      useUi().notify(errorMessage({ code: 'playbackStopped' }), true)
      loadedKey = null
      pendingSeek = null
      audio.pause()
      setPlaying(false)
      return
    }
    // a conversion sent while it is written (no length): a browser that won't take that (Safari
    // may want byte ranges) gets the finished file instead, once
    const src = audio.currentSrc
    if (mayConvert(src) && !src.includes('whole=1')) {
      pendingSeek = audio.currentTime || null
      audio.src = src + '&whole=1'
      if (playing.value) void audio.play().catch(() => {})
      return
    }
    failures++
    // skip a file the browser can't play, but stop instead of running through the whole
    // queue when nothing plays (network down, session expired)
    const network = audio.error?.code === MediaError.MEDIA_ERR_NETWORK || !navigator.onLine
    if (!network && failures < 3 && index.value + 1 < queue.value.length) {
      useUi().notify(errorMessage({ code: 'playback' }), true)
      jump(index.value + 1)
    } else {
      useUi().notify(errorMessage({ code: 'playbackStopped' }), true)
      loadedKey = null // retry from the start of this track on the next play
      audio.pause()
      setPlaying(false)
    }
  })

  // ---- lock screen / headset controls ----
  function updateMediaSession() {
    if (!('mediaSession' in navigator)) return
    const t = i18n.global.t
    const b = book.value
    if (mode.value === 'live' && station.value) {
      navigator.mediaSession.metadata = new MediaMetadata({
        title: station.value.name,
        artist: t('radio.live'),
        album: t('radio.title'),
        artwork: [{ src: '/icon-512.png', sizes: '512x512', type: 'image/png' }],
      })
      return
    }
    if (mode.value === 'book' && b) {
      navigator.mediaSession.metadata = new MediaMetadata({
        title: chapter.value?.title || b.title,
        artist: b.authors || t('common.unknownArtist'),
        album: b.title,
        artwork: b.has_cover
          ? [
              { src: bookCoverUrl(b.id, 'thumb', b.cover_v), sizes: '300x450', type: 'image/jpeg' },
              { src: bookCoverUrl(b.id, 'large', b.cover_v), sizes: '1000x1500', type: 'image/jpeg' },
            ]
          : [{ src: '/icon-512.png', sizes: '512x512', type: 'image/png' }],
      })
      return
    }
    const track = current.value
    if (!track) return
    navigator.mediaSession.metadata = new MediaMetadata({
      title: track.title,
      artist: track.artist || t('common.unknownArtist'),
      album: track.album,
      artwork:
        track.has_cover && track.album_id
          ? [
              { src: coverUrl(track.album_id, 'thumb', track.cover_v), sizes: '300x300', type: 'image/jpeg' },
              { src: coverUrl(track.album_id, 'large', track.cover_v), sizes: '1000x1000', type: 'image/jpeg' },
            ]
          : [{ src: '/icon-512.png', sizes: '512x512', type: 'image/png' }],
    })
  }

  watch(chapterIndex, () => mode.value === 'book' && updateMediaSession())

  /** Books get ±seconds buttons: iOS shows those only while previous/next track are unset. */
  function bindMediaSession() {
    if (!('mediaSession' in navigator)) return
    const ms = navigator.mediaSession
    const isBook = mode.value === 'book'
    if (mode.value === 'live') {
      // a live station: play and pause only
      const live: [MediaSessionAction, MediaSessionActionHandler | null][] = [
        ['play', () => startLive()], ['pause', () => audio.pause()], ['previoustrack', null], ['nexttrack', null],
        ['seekbackward', null], ['seekforward', null], ['seekto', null],
      ]
      for (const [action, handler] of live) {
        try {
          ms.setActionHandler(action, handler)
        } catch {
          /* unsupported action */
        }
      }
      return
    }
    const handlers: [MediaSessionAction, MediaSessionActionHandler | null][] = [
      ['play', () => (isBook ? resumeBook() : startCurrent())],
      ['pause', () => audio.pause()],
      ['previoustrack', isBook ? null : () => prev()],
      ['nexttrack', isBook ? null : () => next()],
      ['seekbackward', isBook ? (d) => skip(-(d.seekOffset || skipBack.value)) : null],
      ['seekforward', isBook ? (d) => skip(d.seekOffset || skipForward.value) : null],
      // seekTime is within the current file (see setPosition)
      ['seekto', (d) => d.seekTime != null && (isBook ? (audio.currentTime = d.seekTime) : seek(d.seekTime))],
    ]
    for (const [action, handler] of handlers) {
      try {
        ms.setActionHandler(action, handler)
      } catch {
        /* unsupported action */
      }
    }
  }
  bindMediaSession()

  return {
    mode,
    station,
    playStation,
    stopStation,
    book,
    bookPos,
    fileIndex,
    chapters,
    chapterIndex,
    chapter,
    segment,
    rate,
    musicRate,
    playStarts,
    startRadio,
    skipBack,
    skipForward,
    sleepUntil,
    sleepChapter,
    playBook,
    seekBook,
    skip,
    jumpChapter,
    nextChapter,
    prevChapter,
    setSleep,
    saveProgress,
    syncBook,
    queue,
    index,
    current,
    playing,
    currentTime,
    duration,
    shuffle,
    repeat,
    volume,
    blocked,
    airplay,
    showAirPlay,
    restore,
    reset,
    playTracks,
    playAlbum,
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
