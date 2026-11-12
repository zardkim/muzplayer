import type { Directive } from 'vue'

// v-long-press="fn": a finger (or the mouse button) held on the element for a moment runs fn, and
// the tap that ends it does nothing else (the link isn't followed). Moving away or scrolling cancels.
const HOLD_MS = 500
const SLOP = 10 // px a finger may wander while held

interface State {
  fn: (() => void) | null
  timer: number
  x: number
  y: number
  fired: boolean
  off: () => void
}
const states = new WeakMap<HTMLElement, State>()

export const vLongPress: Directive<HTMLElement, (() => void) | null | undefined> = {
  mounted(el, binding) {
    const st: State = { fn: binding.value ?? null, timer: 0, x: 0, y: 0, fired: false, off: () => {} }
    const cancel = () => {
      window.clearTimeout(st.timer)
      st.timer = 0
    }
    const down = (e: PointerEvent) => {
      if (e.button !== 0 || !st.fn) return
      st.fired = false
      st.x = e.clientX
      st.y = e.clientY
      cancel()
      st.timer = window.setTimeout(() => {
        st.timer = 0
        st.fired = true
        navigator.vibrate?.(10)
        st.fn?.()
      }, HOLD_MS)
    }
    const move = (e: PointerEvent) => {
      if (Math.abs(e.clientX - st.x) > SLOP || Math.abs(e.clientY - st.y) > SLOP) cancel()
    }
    // the click after a long press: swallowed (before the link's own handler)
    const click = (e: MouseEvent) => {
      if (!st.fired) return
      st.fired = false
      e.preventDefault()
      e.stopImmediatePropagation()
    }
    const menu = (e: Event) => {
      if (st.fired || st.timer) e.preventDefault() // no "open in new tab" menu over it
    }
    el.addEventListener('pointerdown', down)
    el.addEventListener('pointermove', move)
    el.addEventListener('pointerup', cancel)
    el.addEventListener('pointercancel', cancel)
    el.addEventListener('pointerleave', cancel)
    el.addEventListener('click', click, true)
    el.addEventListener('contextmenu', menu)
    st.off = () => {
      cancel()
      el.removeEventListener('pointerdown', down)
      el.removeEventListener('pointermove', move)
      el.removeEventListener('pointerup', cancel)
      el.removeEventListener('pointercancel', cancel)
      el.removeEventListener('pointerleave', cancel)
      el.removeEventListener('click', click, true)
      el.removeEventListener('contextmenu', menu)
    }
    states.set(el, st)
  },
  updated(el, binding) {
    const st = states.get(el)
    if (st) st.fn = binding.value ?? null
  },
  unmounted(el) {
    states.get(el)?.off()
    states.delete(el)
  },
}
