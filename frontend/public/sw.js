// muzplayer service worker: makes the app installable and opens the UI offline.
// Music and API calls go to the server, except songs saved for offline (src/offline.ts), which
// the player asks for with ?saved=1 and which are answered from the device. Covers with a version in the URL (?v=) never
// change, so they are kept in their own cache and not asked for again.
const CACHE = 'muz-shell-v3' // v3: the muz icons with pink notes
const COVERS = 'muz-covers-v1' // also cleared on logout (stores/auth.ts)
const AUDIO = 'muz-audio-v1' // songs fetched ahead by the page (src/audioCache.ts); not touched here
const OFFLINE = 'muz-offline-v1' // songs saved for offline (src/offline.ts); never trimmed here
const SAVED_PATH = /^\/api\/v1\/tracks\/\d+\/stream$/
const MAX_COVERS = 3000 // about 100 MB of 300px covers; the oldest go first
const COVER_PATH = /^\/api\/v1\/((albums|books)\/\d+\/cover|artists\/\d+\/image)$/
const SHELL = ['/', '/manifest.webmanifest', '/favicon.svg', '/logo.svg', '/icon-192.png', '/cover-placeholder.svg']
const MAX_ASSETS = 400 // the build has about 140 files; the downloads page must stay for offline

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()))
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => ![CACHE, COVERS, AUDIO, OFFLINE].includes(k)).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  )
})

async function trim(cache) {
  const keys = (await cache.keys()).filter((r) => new URL(r.url).pathname.startsWith('/assets/'))
  for (const req of keys.slice(0, Math.max(0, keys.length - MAX_ASSETS))) await cache.delete(req)
}

let added = 0
async function trimCovers(cache) {
  if (++added % 100) return // listing thousands of keys on every new cover would cost more than it saves
  const keys = await cache.keys()
  for (const req of keys.slice(0, Math.max(0, keys.length - MAX_COVERS))) await cache.delete(req)
}

async function cover(req) {
  const cache = await caches.open(COVERS)
  const hit = await cache.match(req)
  if (hit) return hit
  const res = await fetch(req)
  if (res.ok) await cache.put(req, res.clone()).then(() => trimCovers(cache)).catch(() => {}) // storage full: just don't keep it
  return res
}

// a saved song, with byte ranges: Safari plays audio only from a server that answers them
async function saved(req, url) {
  const hit = await (await caches.open(OFFLINE)).match(url.pathname)
  const range = req.headers.get('range')
  if (!hit) return fetch(url.pathname, { credentials: 'same-origin', headers: range ? { range } : {} }) // removed meanwhile
  const blob = await hit.blob()
  const size = blob.size
  const headers = { 'Content-Type': hit.headers.get('content-type') || 'audio/mpeg', 'Accept-Ranges': 'bytes' }
  const m = /^bytes=(\d*)-(\d*)$/.exec((range || '').replace(/\s/g, ''))
  if (!m || (!m[1] && !m[2])) return new Response(blob, { headers: { ...headers, 'Content-Length': String(size) } })
  const start = m[1] ? Number(m[1]) : Math.max(0, size - Number(m[2]))
  const end = m[1] && m[2] ? Math.min(Number(m[2]), size - 1) : size - 1
  if (start > end || start >= size) return new Response(null, { status: 416, headers: { 'Content-Range': `bytes */${size}` } })
  return new Response(blob.slice(start, end + 1), {
    status: 206,
    headers: { ...headers, 'Content-Length': String(end - start + 1), 'Content-Range': `bytes ${start}-${end}/${size}` },
  })
}

self.addEventListener('fetch', (event) => {
  const req = event.request
  const url = new URL(req.url)
  if (req.method !== 'GET' || url.origin !== self.location.origin) return

  // versioned covers: cache first (iOS may still empty this cache when space runs low)
  if (COVER_PATH.test(url.pathname) && url.searchParams.has('v')) {
    event.respondWith(cover(req))
    return
  }
  if (SAVED_PATH.test(url.pathname) && url.searchParams.has('saved')) {
    event.respondWith(saved(req, url))
    return
  }
  if (url.pathname.startsWith('/api/')) return

  // pages: network first, fall back to the cached shell when offline
  if (req.mode === 'navigate') {
    event.respondWith(
      fetch(req)
        .then((res) => {
          const copy = res.clone()
          caches.open(CACHE).then((c) => c.put('/', copy))
          return res
        })
        .catch(() => caches.match('/')),
    )
    return
  }

  // hashed build assets never change: cache first
  if (url.pathname.startsWith('/assets/')) {
    event.respondWith(
      caches.match(req).then(
        (hit) =>
          hit ||
          fetch(req).then((res) => {
            if (res.ok) {
              const copy = res.clone()
              caches.open(CACHE).then((c) => c.put(req, copy).then(() => trim(c)))
            }
            return res
          }),
      ),
    )
    return
  }

  if (SHELL.includes(url.pathname)) {
    event.respondWith(caches.match(req).then((hit) => hit || fetch(req)))
  }
})
