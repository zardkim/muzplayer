import { streamUrl } from './api'

// Songs fetched ahead of time: the next few in the queue are downloaded while the current one
// plays, then played from memory (an object URL), so the change to the next song doesn't wait on
// the network and a short drop in a tunnel doesn't stop the music.
//
// Fetched files are also kept in Cache Storage up to a size limit (oldest first out), so a song
// played again needs no download. Cache Storage needs https; without it songs are only kept in
// memory while they're near the front of the queue. iOS may empty the cache when space runs low.
//
// The object URL is made before the song starts: iOS lets play() run only straight from a tap,
// with no waiting in between, so the player must be able to pick the source without awaiting.
const CACHE = 'muz-audio-v1' // kept by sw.js, cleared on logout (stores/auth.ts)
const INDEX_KEY = 'muz.audioCache' // trackId -> {size, at}: what is cached, for the size limit
type Index = Record<string, { size: number; at: number }>

const ready = new Map<number, string>() // trackId -> object URL
let generation = 0 // a newer prepare() stops an older one between songs

const cacheApi = () => (globalThis.caches && window.isSecureContext ? globalThis.caches : null)

function readIndex(): Index {
  try {
    return JSON.parse(localStorage.getItem(INDEX_KEY) || '{}')
  } catch {
    return {}
  }
}
function writeIndex(index: Index) {
  try {
    localStorage.setItem(INDEX_KEY, JSON.stringify(index))
  } catch {
    /* not kept */
  }
}

/** The ready object URL for a song, or null (then it streams from the server). */
export function cachedSource(trackId: number): string | null {
  return ready.get(trackId) ?? null
}

/** Fetches the next songs one at a time and keeps them ready; drops the rest, except the song
 *  playing now (its URL may still be in use). maxBytes: the cache size limit. */
export async function prepare(currentId: number | null, trackIds: number[], maxBytes: number) {
  const gen = ++generation
  for (const [id, url] of ready) {
    if (id !== currentId && !trackIds.includes(id)) {
      URL.revokeObjectURL(url)
      ready.delete(id)
    }
  }
  for (const id of trackIds) {
    if (gen !== generation) return
    if (ready.has(id)) continue
    try {
      const blob = await load(id, maxBytes)
      if (blob && gen === generation && trackIds.includes(id) && !ready.has(id)) ready.set(id, URL.createObjectURL(blob))
    } catch {
      return // offline or the server said no: try again with the next song change
    }
  }
}

async function load(trackId: number, maxBytes: number): Promise<Blob | null> {
  const url = streamUrl(trackId)
  const caches = cacheApi()
  const cache = caches ? await caches.open(CACHE) : null
  const index = readIndex()
  const hit = await cache?.match(url)
  if (hit) {
    if (index[trackId]) {
      index[trackId].at = Date.now()
      writeIndex(index)
    }
    return hit.blob()
  }
  const res = await fetch(url, { credentials: 'same-origin' })
  if (!res.ok) return null
  const size = Number(res.headers.get('content-length') || 0)
  if (cache && size && size < maxBytes / 4) {
    await cache.put(url, res.clone()).catch(() => {}) // storage full: just don't keep it
    index[trackId] = { size, at: Date.now() }
    await evict(cache, index, maxBytes)
  }
  return res.blob()
}

async function evict(cache: Cache, index: Index, maxBytes: number) {
  let total = Object.values(index).reduce((n, e) => n + e.size, 0)
  for (const [id, e] of Object.entries(index).sort((a, b) => a[1].at - b[1].at)) {
    if (total <= maxBytes) break
    await cache.delete(streamUrl(Number(id))).catch(() => {})
    delete index[id]
    total -= e.size
  }
  writeIndex(index)
}

/** Bytes kept in the cache (as recorded when the songs were stored). */
export function cacheUsage(): number {
  return Object.values(readIndex()).reduce((n, e) => n + e.size, 0)
}

/** Empties the cache; the songs near the front of the queue stay ready unless `all`. */
export async function clearAudioCache(all = false) {
  if (all) {
    generation++
    for (const url of ready.values()) URL.revokeObjectURL(url)
    ready.clear()
  }
  writeIndex({})
  await cacheApi()?.delete(CACHE).catch(() => {})
}

/** On mobile data (Android tells us; iPhone doesn't, so it counts as Wi-Fi). */
export function onCellular(): boolean {
  const c = (navigator as Navigator & { connection?: { type?: string } }).connection
  return c?.type === 'cellular'
}
