import { ref, watch } from 'vue'
import { useAuth } from './stores/auth'

// Recent searches, on this device and for each account (the search box and the search page show
// them). The newest first, each once, at most MAX.
const MAX = 10
const recent = ref<string[]>([])
let loadedFor: number | null | undefined

const key = (userId: number) => `muz.searches.${userId}`

function sync() {
  const id = useAuth().user?.id ?? null
  if (id === loadedFor) return
  loadedFor = id
  try {
    recent.value = id === null ? [] : JSON.parse(localStorage.getItem(key(id)) || '[]')
  } catch {
    recent.value = []
  }
}
function save() {
  const id = useAuth().user?.id
  if (id == null) return
  try {
    localStorage.setItem(key(id), JSON.stringify(recent.value))
  } catch {
    /* private window: kept for this visit only */
  }
}

export function useSearchHistory() {
  sync()
  watch(() => useAuth().user?.id, sync)
  return {
    recent,
    add(q: string) {
      const text = q.trim()
      if (!text) return
      const same = text.toLocaleLowerCase()
      recent.value = [text, ...recent.value.filter((r) => r.toLocaleLowerCase() !== same)].slice(0, MAX)
      save()
    },
    remove(q: string) {
      recent.value = recent.value.filter((r) => r !== q)
      save()
    },
    clear() {
      recent.value = []
      save()
    },
  }
}
