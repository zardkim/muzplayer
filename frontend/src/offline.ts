import { reactive } from 'vue'
import { coverUrl } from './api'
import { trackSrc, streamBase } from './stream'
import type { Track } from './types'

// Albums and playlists saved on this device, to play without a connection (the download button;
// the list is Library → downloads). Songs go into their own Cache Storage bucket, never trimmed
// (sw.js keeps it, logout empties it), at the quality being played when they were saved. The
// lists and their songs are kept here too, so the downloads page needs no server.
//
// iOS may still clear a home-screen app's storage when space runs low; persist() asks it not to.
const CACHE = 'muz-offline-v1'
const INDEX_KEY = 'muz.offline'

export interface SavedList {
  key: string // "album:12", "playlist:5"
  title: string
  subtitle: string
  cover: { albumId: number; hasCover: boolean; v?: number } | null // CoverArt's (versioned URLs: sw.js keeps them)
  link: string // where the list is in the app
  tracks: Track[]
  at: number
}
interface Index {
  lists: SavedList[]
  files: Record<string, number> // trackId -> bytes saved
}

function readIndex(): Index {
  try {
    const raw = JSON.parse(localStorage.getItem(INDEX_KEY) || 'null')
    if (raw?.lists && raw?.files) return raw
  } catch {
    /* none */
  }
  return { lists: [], files: {} }
}

export const offline = reactive({
  ...readIndex(),
  progress: {} as Record<string, { done: number; total: number }>, // lists being saved now
})

function writeIndex() {
  try {
    localStorage.setItem(INDEX_KEY, JSON.stringify({ lists: offline.lists, files: offline.files }))
  } catch {
    /* storage full: the songs are still in the cache, but won't be listed after a reload */
  }
}

const cacheApi = () => (globalThis.caches && window.isSecureContext ? globalThis.caches : null)
/** Saving needs Cache Storage, so https (or localhost). */
export const canSave = () => cacheApi() !== null

export const savedList = (key: string) => offline.lists.find((l) => l.key === key) ?? null
export const isSaved = (trackId: number) => String(trackId) in offline.files
export const savedBytes = () => Object.values(offline.files).reduce((n, b) => n + b, 0)

/** Saves a list's songs (those not saved yet), one at a time; saving the same list again
 *  replaces it with what it holds now. Throws when the connection drops (what was fetched stays). */
export async function saveList(list: Omit<SavedList, 'at'>) {
  const caches = cacheApi()
  if (!caches || offline.progress[list.key]) return
  void navigator.storage?.persist?.().catch(() => {})
  const tracks = list.tracks.filter((t) => !t.missing)
  offline.lists = [{ ...list, tracks, at: Date.now() }, ...offline.lists.filter((l) => l.key !== list.key)]
  writeIndex()
  const progress = (offline.progress[list.key] = { done: 0, total: tracks.length })
  warmDownloadsPage()
  try {
    const cache = await caches.open(CACHE)
    const c = list.cover
    if (c?.hasCover && c.v) {
      for (const size of ['thumb', 'large'] as const) await fetch(coverUrl(c.albumId, size, c.v), { credentials: 'same-origin' }).catch(() => {}) // into sw.js's cover cache
    }
    for (const t of tracks) {
      if (!isSaved(t.id)) {
        const res = await fetch(trackSrc(t), { credentials: 'same-origin' })
        if (!res.ok) throw new Error(String(res.status))
        const blob = await res.blob()
        await cache.put(streamBase(t.id), new Response(blob, { headers: { 'Content-Type': res.headers.get('content-type') || 'audio/mpeg' } }))
        offline.files[t.id] = blob.size
        writeIndex()
      }
      progress.done++
    }
  } finally {
    delete offline.progress[list.key]
  }
}

/** Fetches the downloads page's code while online, so it opens offline (sw.js keeps it). */
export function warmDownloadsPage() {
  if (offline.lists.length) void import('./views/DownloadsView.vue').catch(() => {})
}

/** Removes a list; its songs go unless another saved list has them. */
export async function removeList(key: string) {
  offline.lists = offline.lists.filter((l) => l.key !== key)
  const kept = new Set(offline.lists.flatMap((l) => l.tracks.map((t) => String(t.id))))
  const cache = await cacheApi()?.open(CACHE)
  for (const id of Object.keys(offline.files)) {
    if (kept.has(id)) continue
    await cache?.delete(streamBase(Number(id))).catch(() => {})
    delete offline.files[id]
  }
  writeIndex()
}

/** The saved file of a song, or null. */
export async function savedFile(trackId: number): Promise<Blob | null> {
  if (!isSaved(trackId)) return null
  const hit = await (await cacheApi()?.open(CACHE))?.match(streamBase(trackId))
  return hit ? hit.blob() : null
}

/** Logout: the next person on this device shouldn't find them. */
export async function clearSaved() {
  offline.lists = []
  offline.files = {}
  writeIndex()
  await cacheApi()?.delete(CACHE).catch(() => {})
}
