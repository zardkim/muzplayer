import { computed, onActivated, onDeactivated, onUnmounted, ref, watch, type Ref } from 'vue'

// Long lists render a screenful at once and the rest a few rows per frame, so opening a page or
// switching menus doesn't freeze a phone while hundreds of rows (with their covers) are built.
// A new list starts over; rows appended to the same list ("load more") keep going from where it was.
const FIRST = 24
const STEP = 16

export function useProgressive<T>(source: () => T[]): Ref<T[]> {
  const count = ref(FIRST)
  let frame = 0
  let paused = false

  function stop() {
    if (frame) cancelAnimationFrame(frame)
    frame = 0
  }
  function grow() {
    frame = 0
    if (paused || count.value >= source().length) return
    count.value += STEP
    frame = requestAnimationFrame(grow)
  }
  function schedule() {
    if (!frame && !paused && count.value < source().length) frame = requestAnimationFrame(grow)
  }

  watch(source, (list, old) => {
    if (list !== old) count.value = FIRST
    schedule()
  }, { immediate: true })
  watch(() => source().length, schedule)

  // kept-alive pages stop growing while hidden and finish when shown again
  onDeactivated(() => {
    paused = true
    stop()
  })
  onActivated(() => {
    paused = false
    schedule()
  })
  onUnmounted(stop)

  return computed(() => {
    const list = source()
    return list.length > count.value ? list.slice(0, count.value) : list
  })
}
