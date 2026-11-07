import { ref, watch } from 'vue'
import { api } from './api'
import { useAuth } from './stores/auth'
import type { Album, Book, Chart, VideoListItem } from './types'

// What's new since this person last looked (api/news.py): the bell's count, and the news page's lists.
// Asked for on starting and whenever the app comes back to the front (not more than every few
// minutes); the server keeps up to when they've seen it, so their other devices agree.
export interface News {
  since: string
  until: string
  total: number
  counts: Partial<Record<'albums' | 'books' | 'videos' | 'charts' | 'themes', number>>
  albums: Album[]
  books: Book[]
  videos: VideoListItem[]
  charts: Chart[]
}

export const news = ref<News | null>(null)
const AGAIN_AFTER = 3 * 60_000
let askedAt = 0

export async function loadNews(force = false) {
  if (!force && Date.now() - askedAt < AGAIN_AFTER) return news.value
  askedAt = Date.now()
  try {
    news.value = await api<News>('/me/news')
  } catch {
    /* offline: the bell keeps what it had */
  }
  return news.value
}

/** The news page was looked at: seen up to when its lists were made (what came after stays new). */
export async function markNewsSeen() {
  const n = news.value
  if (!n?.total) return
  try {
    await api('/me/news/seen', { method: 'POST', body: { until: n.until } })
    news.value = { ...n, total: 0, counts: {} }
  } catch {
    /* tried again next time */
  }
}

export function startNews() {
  const auth = useAuth()
  watch(
    () => auth.user?.id ?? null,
    (id) => {
      news.value = null
      if (id !== null) loadNews(true)
    },
    { immediate: true },
  )
  document.addEventListener('visibilitychange', () => document.visibilityState === 'visible' && auth.user && loadNews())
}
