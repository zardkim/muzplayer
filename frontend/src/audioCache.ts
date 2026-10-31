import { savedFile } from './offline'
import { streamBase } from './stream'

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
//
// Songs are fetched from the address the player would play them from (stream.ts: quality,
// levelling), and only stand in for that address; a song saved for offline (offline.ts) stands
// in for any.
const CACHE = 'muz-audio-v1' // kept by sw.js, cleared on logout (stores/auth.ts)
const INDEX_KEY = 'muz.audioCache' // trackId -> {size, at, url}: what is cached, for the size limit
type Index = Record<string, { size: number; at: number; url?: string }>
type Ready = { src: string; url: string; saved: boolean } // src: the address it stands in for

const ready = new Map<number, Ready>()
let generation = 0 // a newer prepare() stops an older one between songs
// ...and its download in progress: the server stops a conversion nobody waits for any more
let fetching = new AbortController()

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

/** The ready object URL for a song played from `src`, or null (then it streams from the server). */
export function cachedSource(trackId: number, src: string): string | null {
  const r = ready.get(trackId)
  return r && (r.saved || r.src === src) ? r.url : null
}

/** Fetches the next songs one at a time and keeps them ready; drops the rest, except the song
 *  playing now (its URL may still be in use) and `keep` (the song a crossfade is fading out).
 *  maxBytes: the cache size limit. */
export async function prepare(currentId: number | null, next: { id: number; src: string }[], maxBytes: number, keep: number | null = null) {
  const gen = ++generation
  fetching.abort()
  const signal = (fetching = new AbortController()).signal
  const wanted = new Map(next.map((n) => [n.id, n.src]))
  for (const [id, r] of ready) {
    const src = wanted.get(id)
    if (id !== currentId && id !== keep && (src === undefined || (src !== r.src && !r.saved))) {
      URL.revokeObjectURL(r.url)
      ready.delete(id)
    }
  }
  for (const { id, src } of next) {
    if (gen !== generation) return
    if (ready.has(id)) continue
    try {
      const got = await load(id, src, maxBytes, signal)
      if (got && gen === generation && wanted.has(id) && !ready.has(id)) ready.set(id, { src, url: URL.createObjectURL(got.blob), saved: got.saved })
    } catch {
      return // offline or the server said no: try again with the next song change
    }
  }
}

async function load(trackId: number, src: string, maxBytes: number, signal: AbortSignal): Promise<{ blob: Blob; saved: boolean } | null> {
  const saved = await savedFile(trackId).catch(() => null)
  if (saved) return { blob: saved, saved: true }
  const caches = cacheApi()
  const cache = caches ? await caches.open(CACHE) : null
  const index = readIndex()
  const hit = await cache?.match(src)
  if (hit) {
    if (index[trackId]) {
      index[trackId].at = Date.now()
      writeIndex(index)
    }
    return { blob: await hit.blob(), saved: false }
  }
  const res = await fetch(src, { credentials: 'same-origin', signal })
  if (!res.ok) return null
  // a conversion still being written has no length: kept in memory only
  const size = Number(res.headers.get('content-length') || 0)
  if (cache && size && size < maxBytes / 4) {
    const old = index[trackId]?.url
    if (old && old !== src) await cache.delete(old).catch(() => {}) // the same song at another quality
    await cache.put(src, res.clone()).catch(() => {}) // storage full: just don't keep it
    index[trackId] = { size, at: Date.now(), url: src }
    await evict(cache, index, maxBytes)
  }
  return { blob: await res.blob(), saved: false }
}

async function evict(cache: Cache, index: Index, maxBytes: number) {
  let total = Object.values(index).reduce((n, e) => n + e.size, 0)
  for (const [id, e] of Object.entries(index).sort((a, b) => a[1].at - b[1].at)) {
    if (total <= maxBytes) break
    await cache.delete(e.url ?? streamBase(Number(id))).catch(() => {})
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
    fetching.abort()
    for (const r of ready.values()) URL.revokeObjectURL(r.url)
    ready.clear()
  }
  writeIndex({})
  await cacheApi()?.delete(CACHE).catch(() => {})
}
