<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { Star } from '@lucide/vue'

// 1-5 stars. Tapping the current star clears the rating. With a mouse, pointing at a star
// previews that rating (filled up to it, slightly larger) before clicking.
const props = withDefaults(defineProps<{ value: number | null; size?: number; label?: string }>(), { size: 22 })
const emit = defineEmits<{ rate: [stars: number | null] }>()
const { t } = useI18n()
const hover = ref<number | null>(null)
const shown = computed(() => hover.value ?? props.value ?? 0)

function enter(e: PointerEvent, n: number) {
  if (e.pointerType === 'mouse') hover.value = n // touch has no hover: it would stick after a tap
}
</script>

<template>
  <div class="flex items-center" role="group" :aria-label="label ?? t('common.rating')" @pointerleave="hover = null">
    <button
      v-for="n in 5"
      :key="n"
      type="button"
      class="grid place-items-center transition-[color,transform] duration-100"
      :class="[
        shown >= n ? (hover !== null ? 'text-accent/80' : 'text-accent') : 'text-line-strong',
        hover === n ? 'scale-125' : '',
      ]"
      :style="{ width: `${size + 10}px`, height: `${size + 18}px` }"
      :aria-label="value === n ? t('common.clearRating') : t('common.rateStars', { n })"
      :aria-pressed="value === n"
      @pointerenter="(e) => enter(e, n)"
      @click="emit('rate', props.value === n ? null : n)"
    >
      <Star :size="size" :stroke-width="1.4" :fill="shown >= n ? 'currentColor' : 'none'" />
    </button>
  </div>
</template>
