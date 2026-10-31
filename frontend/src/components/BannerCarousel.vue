<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ChevronLeft, ChevronRight } from '@lucide/vue'
import type { Chart } from '../types'
import BannerCard from './BannerCard.vue'

// Swipeable banners (CSS scroll snap). Moves on by itself every 5 s unless the viewer is
// touching/hovering it, the tab is hidden, or the system asks for reduced motion.
const props = withDefaults(defineProps<{ items: Chart[]; size?: 'hero' | 'compact' }>(), { size: 'hero' })
const { t } = useI18n()
const track = ref<HTMLElement | null>(null)
const index = ref(0)
let timer: number | undefined
let holdUntil = 0

function onScroll() {
  const el = track.value
  if (el) index.value = Math.round(el.scrollLeft / el.clientWidth)
}

function go(i: number) {
  const el = track.value
  if (!el) return
  el.scrollTo({ left: i * el.clientWidth, behavior: 'smooth' })
}

function hold() {
  holdUntil = Date.now() + 8000
}

/** The arrows: one slide back or on, round the ends. */
function step(by: number) {
  hold()
  go((index.value + by + props.items.length) % props.items.length)
}

onMounted(() => {
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
  timer = window.setInterval(() => {
    if (Date.now() < holdUntil || document.hidden || props.items.length < 2) return
    go((index.value + 1) % props.items.length)
  }, 5000)
})
onUnmounted(() => clearInterval(timer))
</script>

<template>
  <section class="relative" :aria-label="t('charts.featured')" aria-roledescription="carousel">
    <div
      ref="track"
      class="flex snap-x snap-mandatory overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
      @scroll.passive="onScroll"
      @touchstart.passive="hold"
      @pointerenter="hold"
      @pointermove="hold"
      @focusin="hold"
    >
      <div
        v-for="(c, i) in items"
        :key="c.id"
        class="w-full flex-none snap-center px-0.5"
        role="group"
        aria-roledescription="slide"
        :aria-label="`${i + 1} / ${items.length}`"
      >
        <BannerCard :chart="c" :size="size" />
      </div>
    </div>
    <template v-if="items.length > 1">
      <button
        v-for="by in [-1, 1]"
        :key="by"
        type="button"
        class="absolute top-[calc(50%-0.6875rem)] grid size-10 -translate-y-1/2 place-items-center rounded-full bg-bg/85 text-ink shadow-md backdrop-blur-sm transition-opacity hover:bg-bg md:size-11"
        :class="by < 0 ? 'left-2 md:left-3' : 'right-2 md:right-3'"
        :aria-label="t(by < 0 ? 'charts.slidePrev' : 'charts.slideNext')"
        @click="step(by)"
      >
        <component :is="by < 0 ? ChevronLeft : ChevronRight" :size="22" :stroke-width="1.6" />
      </button>
    </template>
    <div v-if="items.length > 1" class="mt-2.5 flex justify-center gap-1.5">
      <button
        v-for="(c, i) in items"
        :key="c.id"
        type="button"
        class="h-1.5 rounded-full transition-all"
        :class="i === index ? 'w-5 bg-ink' : 'w-1.5 bg-line-strong'"
        :aria-label="`${i + 1}: ${c.title}`"
        :aria-current="i === index"
        @click="hold(), go(i)"
      />
    </div>
  </section>
</template>
