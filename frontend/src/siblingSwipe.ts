import { computed, nextTick, ref, watch, type Ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

// Phone: on a page opened from a list (an album from the albums, an artist, a chart, an audiobook,
// a genre, a folder, a playlist...), a sideways swipe opens the next or the previous one of that
// list. The list is whatever the tapped link sat among: the links of the same kind around it, in
// the order shown. Swiping replaces the page, so back still goes to the list.
//
// Only sideways: up and down scroll the page (and pull it to refresh at the top).

interface Sibling { path: string; label: string }

const DETAIL = ['/albums/:', '/artists/:', '/charts/:', '/books/:', '/playlists/:', '/video-playlists/:', '/mixes/:', '/tracks?genre', '/folders?path']
const FAR = 90 // px: a swipe this long counts (or a flick that way)

function parse(href: string) {
  const u = new URL(href, location.origin)
  const parts = u.pathname.split('/').filter(Boolean)
  const base = parts.length > 1 ? `/${parts.slice(0, -1).join('/')}/:` : u.pathname
  const keys = [...u.searchParams.keys()].sort().join('&')
  return { path: u.pathname + u.search, kind: keys ? `${base}?${keys}` : base }
}

let siblings: Sibling[] = []

/** A link was tapped: its list is the smallest box around it with other links of its kind. */
function remember(e: MouseEvent, root: HTMLElement) {
  const link = (e.target as Element | null)?.closest('a[href]') as HTMLAnchorElement | null
  if (!link || !root.contains(link)) return
  const { kind } = parse(link.getAttribute('href')!)
  if (!DETAIL.includes(kind)) return
  const found = (box: Element) => {
    const out = new Map<string, string>()
    for (const a of box.querySelectorAll<HTMLAnchorElement>('a[href]')) {
      const p = parse(a.getAttribute('href')!)
      if (p.kind !== kind || out.has(p.path)) continue
      const text = (a.getAttribute('aria-label') || a.innerText || '').split('\n').map((s) => s.trim()).find(Boolean) ?? ''
      out.set(p.path, text.slice(0, 40))
    }
    return out
  }
  let box: Element | null = link.parentElement
  let items = new Map<string, string>()
  while (box && root.contains(box)) {
    items = found(box)
    if (items.size > 1) break
    box = box === root ? null : box.parentElement
  }
  siblings = [...items].map(([path, label]) => ({ path, label }))
}

/** Inside something that scrolls sideways (a row of covers), or a slider: that gesture is its own. */
function ownsSideways(target: Element | null, root: HTMLElement) {
  if (target?.closest('input[type=range], [data-no-swipe]')) return true
  for (let el = target as HTMLElement | null; el && el !== root; el = el.parentElement) {
    if (el.scrollWidth > el.clientWidth + 2 && /auto|scroll/.test(getComputedStyle(el).overflowX)) return true
  }
  return false
}

export function useSiblingSwipe(el: Ref<HTMLElement | null>) {
  const route = useRoute()
  const router = useRouter()
  // for the hint at the edge (SwipeHint.vue), updated once a frame: which way, and how far of FAR
  const dir = ref<-1 | 0 | 1>(0)
  const progress = ref(0)
  const here = () => siblings.findIndex((s) => s.path === parse(route.fullPath).path)
  const next = (d: number) => {
    const i = here()
    return i < 0 || d === 0 ? null : (d < 0 ? siblings[i + 1] : siblings[i - 1]) ?? null
  }
  // what the swipe under way would open: to the left the next one, to the right the previous one
  const target = computed(() => next(dir.value))
  const ready = computed(() => progress.value >= 1)

  let x0 = 0
  let y0 = 0
  let dx = 0
  let tracking = false
  let sideways: boolean | null = null
  let busy = false // a page sliding out or in
  let frame = 0
  let samples: [number, number][] = [] // the last moves (time, x), for the speed at release

  /** The page where the finger has it: 1:1 when there is a page that way, a rubber band when not. */
  function follow() {
    frame = 0
    if (!el.value) return
    const d = dx < 0 ? -1 : dx > 0 ? 1 : 0
    const w = el.value.clientWidth || window.innerWidth
    const x = next(d) ? dx : d * (1 - 1 / ((Math.abs(dx) * 0.55) / w + 1)) * w * 0.5
    el.value.style.transition = ''
    el.value.style.transform = `translate3d(${x}px,0,0)`
    dir.value = d
    progress.value = Math.min(1, Math.abs(dx) / FAR)
  }
  function slide(x: number, ms: number, ease: string, opacity = 1) {
    const box = el.value
    if (!box) return Promise.resolve()
    box.style.transition = `transform ${ms}ms ${ease}, opacity ${ms}ms ${ease}`
    box.style.transform = `translate3d(${x}px,0,0)`
    box.style.opacity = String(opacity)
    return new Promise<void>((done) => window.setTimeout(done, ms))
  }
  function clear() {
    const box = el.value
    if (!box) return
    box.style.transition = box.style.transform = box.style.opacity = box.style.willChange = ''
  }

  function start(e: TouchEvent) {
    tracking = false
    if (busy || e.touches.length !== 1 || !el.value) return
    const x = e.touches[0].clientX
    // the screen's edges belong to the browser's own back / forward swipe
    if (x < 20 || x > window.innerWidth - 20) return
    if (here() < 0) return
    if (ownsSideways(e.target as Element, el.value)) return
    tracking = true
    sideways = null
    dx = 0
    x0 = x
    y0 = e.touches[0].clientY
    samples = [[performance.now(), x]]
  }
  function move(e: TouchEvent) {
    if (!tracking) return
    const x = e.touches[0].clientX
    const mx = x - x0
    const my = e.touches[0].clientY - y0
    if (sideways === null) {
      if (Math.abs(mx) < 8 && Math.abs(my) < 8) return
      sideways = Math.abs(mx) > Math.abs(my) * 1.2
      if (!sideways) {
        tracking = false
        return
      }
      el.value!.style.willChange = 'transform'
    }
    if (e.cancelable) e.preventDefault() // no scrolling up and down under a sideways swipe
    dx = mx
    samples.push([performance.now(), x])
    if (samples.length > 5) samples.shift()
    if (!frame) frame = requestAnimationFrame(follow)
  }
  async function end() {
    if (!tracking || !sideways) return
    tracking = false
    cancelAnimationFrame(frame)
    frame = 0
    const [t1, xa] = samples[0]
    const [t2, xb] = samples[samples.length - 1]
    const speed = (xb - xa) / Math.max(1, t2 - t1) // px per ms, + to the right
    const d = dx < 0 ? -1 : 1
    const to = next(d)
    // far enough, or flung that way
    const go = to && (Math.abs(dx) > FAR || (speed * d > 0.35 && Math.abs(dx) > 40))
    dir.value = 0
    progress.value = 0
    if (!go) {
      await slide(0, 320, 'cubic-bezier(0.2, 0.9, 0.3, 1)')
      clear()
      return
    }
    busy = true
    const w = el.value?.clientWidth || window.innerWidth
    // out the way it was going (quicker when flung), the next one in from the other side
    await slide(d * w, Math.max(140, Math.min(260, (w - Math.abs(dx)) / Math.max(0.8, Math.abs(speed)))), 'cubic-bezier(0.2, 0.7, 0.4, 1)', 0.4)
    await router.replace(to!.path).catch(() => {})
    await nextTick()
    const box = el.value
    if (box) {
      box.style.transition = 'none'
      box.style.transform = `translate3d(${-d * w * 0.35}px,0,0)`
      box.style.opacity = '0'
      void box.offsetWidth // (the start position takes effect before the slide)
      await slide(0, 320, 'cubic-bezier(0.2, 0.9, 0.3, 1)')
    }
    clear()
    busy = false
  }

  watch(
    el,
    (now, old) => {
      if (old) {
        old.removeEventListener('click', onClick, true)
        old.removeEventListener('touchstart', start)
        old.removeEventListener('touchmove', move)
        old.removeEventListener('touchend', end)
        old.removeEventListener('touchcancel', end)
      }
      if (now) {
        now.addEventListener('click', onClick, true)
        now.addEventListener('touchstart', start, { passive: true })
        // not passive: once a swipe is sideways the page must not also scroll
        now.addEventListener('touchmove', move, { passive: false })
        now.addEventListener('touchend', end)
        now.addEventListener('touchcancel', end)
      }
    },
    { immediate: true },
  )
  function onClick(e: MouseEvent) {
    if (el.value) remember(e, el.value)
  }

  return { dir, progress, target, ready }
}
