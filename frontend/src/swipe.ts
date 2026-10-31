// Touch swipes for the players (phones): the finger is followed along one axis, chosen by its
// first 10px of movement, and on release the swipe counts when it went far or fast enough.
// Sliders (seek, volume) and anything marked data-no-swipe (the lyrics, which scroll) are left alone.

export type Axis = 'x' | 'y'
export interface SwipeEnd { axis: Axis; dx: number; dy: number; fast: boolean }
interface Options {
  axes: Axis[]
  /** False to ignore this touch (e.g. the page is scrolled and only a pull from the top counts). */
  allow?: (axis: Axis, dx: number, dy: number) => boolean
  move?: (axis: Axis, dx: number, dy: number) => void
  end?: (s: SwipeEnd) => void
}

export function useSwipe(o: Options) {
  let x0 = 0, y0 = 0, t0 = 0
  let axis: Axis | null = null
  let tracking = false

  function onTouchstart(e: TouchEvent) {
    const target = e.target as Element | null
    tracking = e.touches.length === 1 && !target?.closest('input[type=range], [data-no-swipe]')
    axis = null
    x0 = e.touches[0].clientX
    y0 = e.touches[0].clientY
    t0 = performance.now()
  }
  function onTouchmove(e: TouchEvent) {
    if (!tracking) return
    const dx = e.touches[0].clientX - x0
    const dy = e.touches[0].clientY - y0
    if (!axis) {
      if (Math.abs(dx) < 10 && Math.abs(dy) < 10) return
      const a: Axis = Math.abs(dx) > Math.abs(dy) ? 'x' : 'y'
      if (!o.axes.includes(a) || (o.allow && !o.allow(a, dx, dy))) {
        tracking = false
        return
      }
      axis = a
    }
    if (e.cancelable) e.preventDefault() // the page doesn't scroll (or pull to refresh) under the swipe
    o.move?.(axis, dx, dy)
  }
  function onTouchend(e: TouchEvent) {
    if (!tracking || !axis) return
    tracking = false
    const dx = e.changedTouches[0].clientX - x0
    const dy = e.changedTouches[0].clientY - y0
    const speed = Math.abs(axis === 'x' ? dx : dy) / Math.max(1, performance.now() - t0) // px per ms
    o.end?.({ axis, dx, dy, fast: speed > 0.5 })
    axis = null
  }
  return { onTouchstart, onTouchmove, onTouchend, onTouchcancel: onTouchend }
}

/** A finger held still on something for `ms` (the menu of a song, picking up a queue row). The click
 *  that follows the release is swallowed, so holding a row doesn't also play it. */
export function useLongPress(fire: (target: Element, x: number, y: number) => void, ms = 450) {
  let timer = 0
  let x0 = 0, y0 = 0
  let fired = false
  function cancel() {
    window.clearTimeout(timer)
    timer = 0
  }
  function onTouchstart(e: TouchEvent) {
    cancel()
    fired = false
    if (e.touches.length !== 1) return
    const target = e.target as Element
    x0 = e.touches[0].clientX
    y0 = e.touches[0].clientY
    timer = window.setTimeout(() => {
      timer = 0
      fired = true
      navigator.vibrate?.(12)
      fire(target, x0, y0)
    }, ms)
  }
  function onTouchmove(e: TouchEvent) {
    if (timer && Math.hypot(e.touches[0].clientX - x0, e.touches[0].clientY - y0) > 8) cancel()
  }
  function onTouchend() {
    cancel()
  }
  /** On the element, in the capture phase: drops the click a long press leaves behind. */
  function onClickCapture(e: MouseEvent) {
    if (!fired) return
    fired = false
    e.preventDefault()
    e.stopPropagation()
  }
  return { onTouchstart, onTouchmove, onTouchend, onClickCapture, held: () => fired }
}
