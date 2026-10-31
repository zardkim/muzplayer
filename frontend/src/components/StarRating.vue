<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { Star } from '@lucide/vue'

// 0.5-5 stars in halves: the left half of a star gives n - 0.5, the right half n. Tapping the
// current value clears the rating. With a mouse, pointing previews that rating (slightly larger).
const props = withDefaults(defineProps<{ value: number | null; size?: number; label?: string }>(), { size: 22 })
const emit = defineEmits<{ rate: [stars: number | null] }>()
const { t } = useI18n()
const hover = ref<number | null>(null)
const shown = computed(() => hover.value ?? props.value ?? 0)

function enter(e: PointerEvent, v: number) {
  if (e.pointerType === 'mouse') hover.value = v // touch has no hover: it would stick after a tap
}
const fill = (n: number) => (shown.value >= n ? 'full' : shown.value >= n - 0.5 ? 'half' : 'none')
</script>

<template>
  <div class="flex items-center" role="group" :aria-label="label ?? t('common.rating')" @pointerleave="hover = null">
    <span
      v-for="n in 5"
      :key="n"
      class="relative grid place-items-center transition-[color,transform] duration-100"
      :class="[
        fill(n) !== 'none' ? (hover !== null ? 'text-accent/80' : 'text-accent') : 'text-line-strong',
        hover !== null && Math.ceil(hover) === n ? 'scale-125' : '',
      ]"
      :style="{ width: `${size + 10}px`, height: `${size + 18}px` }"
    >
      <Star :size="size" :stroke-width="1.4" :fill="fill(n) === 'full' ? 'currentColor' : 'none'" />
      <!-- the filled left half of a half star -->
      <Star v-if="fill(n) === 'half'" :size="size" :stroke-width="1.4" fill="currentColor" class="absolute [clip-path:inset(0_50%_0_0)]" />
      <button
        v-for="v in [n - 0.5, n]"
        :key="v"
        type="button"
        class="absolute inset-y-0 w-1/2"
        :class="v === n ? 'right-0' : 'left-0'"
        :aria-label="value === v ? t('common.clearRating') : t('common.rateStars', { n: v })"
        :aria-pressed="value === v"
        @pointerenter="(e) => enter(e, v)"
        @click="emit('rate', props.value === v ? null : v)"
      />
    </span>
  </div>
</template>
