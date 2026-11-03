<script setup lang="ts">
import { nextTick, onMounted, onUnmounted, ref, watch } from 'vue'

// A title too long for its line slides left to show the rest, then back, pausing a moment at each
// end, so all of it can be read; one that fits just sits there. With reduced motion it is cut with …
// instead. `as`: the element (h1 for a page's title).
const props = defineProps<{ text: string; as?: string }>()
const box = ref<HTMLElement | null>(null)
const inner = ref<HTMLElement | null>(null)
const dist = ref(0) // how far it slides (px): what does not fit
const HOLD = 1500 // ms still at each end
const SPEED = 50 // px a second
let anim: Animation | null = null
const still = globalThis.matchMedia?.('(prefers-reduced-motion: reduce)')

function measure() {
  if (!box.value || !inner.value) return
  const d = inner.value.scrollWidth - box.value.clientWidth
  const next = d > 2 ? d : 0
  if (next === dist.value && (anim || !next)) return
  dist.value = next
  anim?.cancel()
  anim = null
  if (!next || still?.matches || !inner.value.animate) return
  const move = (next / SPEED) * 1000
  const total = 2 * move + 2 * HOLD
  const at = (ms: number) => ms / total
  anim = inner.value.animate(
    [
      // (each stretch eases in and out; the whole loop runs at an even pace)
      { transform: 'translateX(0)', offset: 0 },
      { transform: 'translateX(0)', offset: at(HOLD), easing: 'ease-in-out' },
      { transform: `translateX(-${next}px)`, offset: at(HOLD + move) },
      { transform: `translateX(-${next}px)`, offset: at(2 * HOLD + move), easing: 'ease-in-out' },
      { transform: 'translateX(0)', offset: 1 },
    ],
    { duration: total, iterations: Infinity },
  )
}
let ro: ResizeObserver | null = null
onMounted(() => {
  ro = new ResizeObserver(measure)
  ro.observe(box.value!)
  ro.observe(inner.value!)
  measure()
})
onUnmounted(() => {
  ro?.disconnect()
  anim?.cancel()
})
watch(() => props.text, () => void nextTick(measure))
</script>

<template>
  <component
    :is="as ?? 'span'"
    ref="box"
    class="block min-w-0 overflow-hidden text-ellipsis whitespace-nowrap"
    :title="dist ? text : undefined"
  ><span ref="inner" class="inline-block">{{ text }}</span></component>
</template>
