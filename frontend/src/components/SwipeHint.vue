<script setup lang="ts">
import { ChevronRight } from '@lucide/vue'
import type { useSiblingSwipe } from '../siblingSwipe'

// Phone: the page a sideways swipe opens, at the edge it comes in from (dark once far enough).
// Its own component, so a swipe repaints this and not the whole app.
defineProps<{ swipe: ReturnType<typeof useSiblingSwipe> }>()
</script>

<template>
  <div
    v-if="swipe.target.value"
    class="pointer-events-none fixed top-1/2 z-40 flex max-w-[70vw] -translate-y-1/2 items-center gap-1 rounded-full py-2 text-[14px] shadow-[0_2px_10px_rgba(0,0,0,0.18)] transition-colors duration-150 md:hidden"
    :class="[swipe.dir.value < 0 ? 'right-3 pl-4 pr-2.5' : 'left-3 flex-row-reverse pl-2.5 pr-4', swipe.ready.value ? 'bg-ink text-on-ink' : 'bg-bg text-ink']"
    :style="{ opacity: swipe.progress.value, transform: `translate(${(1 - swipe.progress.value) * 12 * swipe.dir.value}px, -50%) scale(${0.92 + swipe.progress.value * 0.08})` }"
    aria-hidden="true"
  >
    <span class="truncate">{{ swipe.target.value.label }}</span>
    <ChevronRight :size="18" :stroke-width="1.8" class="flex-none" :class="swipe.dir.value < 0 ? '' : 'rotate-180'" />
  </div>
</template>
