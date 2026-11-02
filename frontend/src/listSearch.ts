import { ref, watch } from 'vue'
import { useRoute } from 'vue-router'

// What was typed in a list page's search box, by page: a new sort or kind remounts the page (its
// address changes), and the search stays. Cleared when someone else signs in.
const typed = new Map<string, string>()

export function forgetListSearches() {
  typed.clear()
}

/** The page's search text; `changed` runs a moment after typing stops (for a search on the server). */
export function useListSearch(changed?: () => void) {
  const page = String(useRoute().name)
  const q = ref(typed.get(page) ?? '')
  let timer: number | undefined
  watch(q, (v) => {
    typed.set(page, v)
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
