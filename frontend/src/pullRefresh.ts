import { computed, ref, watch, type Ref } from 'vue'

// Pulling the page down from its top on a phone reloads it. The page scrolls inside <main>, not the
// document, so the browser's own pull-to-refresh never comes. Only a downward drag that starts at
// the top counts (a sideways swipe on a row of covers does not).
export const PULL = 70 // how far, after the drag's damping, is a pull

export function usePullRefresh(el: Ref<HTMLElement | null>, refresh: () => void) {
  const pull = ref(0)
  const busy = ref(false)
  let startX = 0
  let startY = 0
  let tracking = false
  let down: boolean | null = null // decided by the first few pixels of the drag

  function start(e: TouchEvent) {
    if (busy.value || e.touches.length !== 1 || !el.value || el.value.scrollTop > 0) return
    tracking = true
    down = null
    startX = e.touches[0].clientX
    startY = e.touches[0].clientY
  }
  function move(e: TouchEvent) {
    if (!tracking || !el.value) return
    const dx = e.touches[0].clientX - startX
    const dy = e.touches[0].clientY - startY
    if (down === null) {
      if (Math.abs(dx) < 8 && Math.abs(dy) < 8) return
      down = dy > 0 && Math.abs(dy) > Math.abs(dx)
    }
    if (!down || el.value.scrollTop > 0) {
      tracking = false
      pull.value = 0
      return
    }
    pull.value = Math.min(dy * 0.5, PULL * 1.4)
  }
  function end() {
    if (!tracking) return
    tracking = false
    if (pull.value < PULL) {
      pull.value = 0
      return
    }
    busy.value = true
    pull.value = PULL
    refresh()
    window.setTimeout(() => {
      busy.value = false
      pull.value = 0
    }, 700)
  }

  watch(
    el,
    (now, old) => {
      old?.removeEventListener('touchstart', start)
      old?.removeEventListener('touchmove', move)
      old?.removeEventListener('touchend', end)
      old?.removeEventListener('touchcancel', end)
      now?.addEventListener('touchstart', start, { passive: true })
      now?.addEventListener('touchmove', move, { passive: true })
      now?.addEventListener('touchend', end)
      now?.addEventListener('touchcancel', end)
    },
    { immediate: true },
  )
  return { pull, busy, ready: computed(() => pull.value >= PULL) }
}
