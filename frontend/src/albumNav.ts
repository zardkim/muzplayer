import { api, query } from './api'
import type { Album, Page } from './types'

// The albums page's order (its sort, kind and search, as far as it has loaded), kept for the album
// page's previous / next album (arrows, ← →, a sideways swipe). Opened from anywhere else, an album
// not in that list has no neighbours. At the end of what was loaded the next page is asked for.

interface Nav { params: Record<string, string | undefined>; ids: number[]; total: number }
let nav: Nav | null = null
let asking: Promise<void> | null = null

export function rememberAlbums(params: Record<string, string | undefined>, items: Album[], total: number) {
  nav = { params, ids: items.map((a) => a.id), total }
}

async function more() {
  const n = nav
  if (!n || n.ids.length >= n.total) return
  asking ??= api<Page<Album>>(`/albums${query({ ...n.params, limit: 120, offset: n.ids.length })}`)
    .then((page) => {
      if (nav !== n) return
      n.ids.push(...page.items.map((a) => a.id).filter((id) => !n.ids.includes(id)))
      n.total = page.total
    })
    .catch(() => {})
    .finally(() => (asking = null))
  await asking
}

/** The albums before and after this one in the albums page's order (null: none, or not from there). */
export async function neighbours(id: number): Promise<{ prev: number | null; next: number | null; index: number; total: number } | null> {
  if (!nav) return null
  let i = nav.ids.indexOf(id)
  if (i < 0) return null
  if (i === nav.ids.length - 1) {
    await more()
    if (!nav) return null
    i = nav.ids.indexOf(id)
  }
  return { prev: i > 0 ? nav.ids[i - 1] : null, next: nav.ids[i + 1] ?? null, index: i, total: nav.total }
}
