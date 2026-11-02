import { computed, ref, watch, type Ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

// Phone: on a page opened from a list (an album from the albums, an artist, a chart, an audiobook,
// a genre, a folder, a playlist...), a sideways swipe opens the next or the previous one of that
// list. The list is whatever the tapped link sat among: the links of the same kind around it, in
// the order shown. Swiping replaces the page, so back still goes to the list.
//
// Only sideways: up and down scroll the page (and pull it to refresh at the top).

interface Sibling { path: string; label: string }

const DETAIL = ['/albums/:', '/artists/:', '/charts/:', '/books/:', '/playlists/:', '/video-playlists/:', '/mixes/:', '/tracks?genre', '/folders?path']
const FAR = 90 // px: a swipe this long counts (or a quick one of half that)

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
  const dx = ref(0)
  const settling = ref(false)
  const here = () => siblings.findIndex((s) => s.path === parse(route.fullPath).path)
  // what the swipe under way would open: to the left the next one, to the right the previous one
  const target = computed(() => {
    const i = dx.value === 0 ? -1 : here()
    if (i < 0) return null
    return dx.value < 0 ? siblings[i + 1] ?? null : siblings[i - 1] ?? null
  })

  let x0 = 0
  let y0 = 0
  let t0 = 0
  let tracking = false
  let sideways: boolean | null = null

  function start(e: TouchEvent) {
    tracking = false
    if (e.touches.length !== 1 || !el.value) return
    const x = e.touches[0].clientX
    // the screen's edges belong to the browser's own back / forward swipe
    if (x < 20 || x > window.innerWidth - 20) return
    if (here() < 0) return
    if (ownsSideways(e.target as Element, el.value)) return
    tracking = true
    sideways = null
    x0 = x
    y0 = e.touches[0].clientY
    t0 = performance.now()
  }
  function move(e: TouchEvent) {
    if (!tracking) return
    const mx = e.touches[0].clientX - x0
    const my = e.touches[0].clientY - y0
    if (sideways === null) {
      if (Math.abs(mx) < 10 && Math.abs(my) < 10) return
      sideways = Math.abs(mx) > Math.abs(my) * 1.5
      if (!sideways) {
        tracking = false
        return
      }
    }
    dx.value = mx
  }
  function end() {
    if (!tracking || !sideways) return
    tracking = false
    const fast = Math.abs(dx.value) / Math.max(1, performance.now() - t0) > 0.5
    const go = target.value && (Math.abs(dx.value) > FAR || (fast && Math.abs(dx.value) > FAR / 2))
    if (go) void router.replace(target.value!.path)
    settling.value = true
    dx.value = 0
    window.setTimeout(() => (settling.value = false), 200)
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
        now.addEventListener('touchmove', move, { passive: true })
        now.addEventListener('touchend', end)
        now.addEventListener('touchcancel', end)
      }
    },
    { immediate: true },
  )
  function onClick(e: MouseEvent) {
    if (el.value) remember(e, el.value)
  }

  // the page follows the finger a little (less where there is nothing more that way)
  const shift = computed(() => (dx.value === 0 ? 0 : target.value ? dx.value * 0.35 : dx.value * 0.12))
  const ready = computed(() => Math.abs(dx.value) > FAR)
  return { dx, shift, target, ready, settling }
}
