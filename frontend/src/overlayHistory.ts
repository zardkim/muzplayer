import { watch } from 'vue'
import type { Router } from 'vue-router'

type Layer = { open: () => boolean; close: () => void }
const KEY = 'muzOverlay'

// Sheets over the page (the phone player, the queue, pickers) get a history entry while open, so the
// back button or gesture closes the top one instead of leaving the page underneath.
// - closed by its own button / Esc / swipe: our entry is taken off again (history.back)
// - a link followed from inside a sheet replaces our entry, so back then returns to the page under it
export function useOverlayHistory(router: Router, layers: Layer[]) {
  const stack: Layer[] = [] // open layers, last opened on top
  let token: number | null = null // marks our entry while one is in the history
  const onOurEntry = () => token !== null && window.history.state?.[KEY] === token

  function sync() {
    if (stack.length && token === null) {
      token = Date.now()
      window.history.pushState({ ...window.history.state, [KEY]: token }, '')
    } else if (!stack.length && token !== null) {
      const ours = onOurEntry()
      token = null
      if (ours) window.history.back()
    }
  }

  for (const layer of layers) {
    watch(layer.open, (open) => {
      const i = stack.indexOf(layer)
      if (open && i < 0) stack.push(layer)
      else if (!open && i >= 0) stack.splice(i, 1)
      sync()
    })
  }

  // back: our entry is gone; close the top layer (if others stay open, sync adds a new entry)
  window.addEventListener('popstate', () => {
    if (token === null || onOurEntry()) return
    token = null
    stack.at(-1)?.close()
  })

  router.beforeEach((to, from) => {
    if (!onOurEntry() || to.redirectedFrom || to.fullPath === from.fullPath) return
    token = null
    return { path: to.path, query: to.query, hash: to.hash, replace: true }
  })
}
