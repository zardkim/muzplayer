<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ChevronLeft, ChevronRight } from '@lucide/vue'

// Left/right arrows over a horizontal row (charts, albums...) on wide screens, where a mouse
// can't swipe it: each moves the row on by most of its width. Hidden at an end.
const props = defineProps<{ row: HTMLElement | null }>()
const { t } = useI18n()
const atStart = ref(true)
const atEnd = ref(true)

function update() {
  const el = props.row
  if (!el) return
  atStart.value = el.scrollLeft < 4
  atEnd.value = el.scrollLeft + el.clientWidth >= el.scrollWidth - 4
}
function move(by: number) {
  const el = props.row
  el?.scrollBy({ left: by * el.clientWidth * 0.8, behavior: 'smooth' })
}
let observer: ResizeObserver | null = null
onMounted(() => {
  const el = props.row
  if (!el) return
  el.addEventListener('scroll', update, { passive: true })
  observer = new ResizeObserver(update)
  observer.observe(el)
  update()
})
onUnmounted(() => {
  props.row?.removeEventListener('scroll', update)
  observer?.disconnect()
})
</script>

<template>
  <button
    v-for="by in [-1, 1]"
    v-show="by < 0 ? !atStart : !atEnd"
    :key="by"
    type="button"
    class="absolute top-[38%] z-10 hidden size-10 -translate-y-1/2 place-items-center rounded-full border border-line bg-bg/90 text-ink shadow-md backdrop-blur-sm hover:bg-bg md:grid"
    :class="by < 0 ? '-left-4' : '-right-4'"
    :aria-label="t(by < 0 ? 'charts.slidePrev' : 'charts.slideNext')"
    @click="move(by)"
  >
    <component :is="by < 0 ? ChevronLeft : ChevronRight" :size="20" :stroke-width="1.6" />
  </button>
</template>
