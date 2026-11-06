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
