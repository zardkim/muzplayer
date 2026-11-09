import { computed, reactive, watch } from 'vue'
import { useRoute } from 'vue-router'

// What was typed in a list page's search box, by page: a new sort or kind remounts the page (its
// address changes), and the search stays. Cleared when someone else signs in. The library's tabs
// are searched from the top bar on a PC (App.vue binds it with listSearchFor).
const typed = reactive(new Map<string, string>())

export function forgetListSearches() {
  typed.clear()
}

/** The search text kept for the page named `page`. */
export function listSearchFor(page: () => string) {
  return computed({
    get: () => typed.get(page()) ?? '',
    set: (v: string) => void typed.set(page(), v),
  })
}

/** The page's search text; `changed` runs a moment after typing stops (for a search on the server). */
export function useListSearch(changed?: () => void) {
  const page = String(useRoute().name)
  const q = listSearchFor(() => page)
  let timer: number | undefined
  watch(q, () => {
    if (!changed) return
    clearTimeout(timer)
    timer = window.setTimeout(changed, 300)
  })
  return q
}

/** Does `text` contain what was typed (any case)? */
export function matches(text: string, q: string) {
  return !q.trim() || text.toLowerCase().includes(q.trim().toLowerCase())
}

const squash = (text: string) => text.normalize('NFKC').toLowerCase().replace(/[\s\p{P}]+/gu, '')

/** The other name an artist was found by, when its own name doesn't have what was typed
 *  ("머라이어" finds Mariah Carey by 머라이어 캐리): shown with it, so the result makes sense. */
export function aliasHit(artist: { name: string; aliases?: string[] }, q: string): string | null {
  const want = squash(q)
  if (!want || squash(artist.name).includes(want)) return null
  return artist.aliases?.find((a) => squash(a).includes(want)) ?? null
}
