<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { Star } from '@lucide/vue'

// 1-5 stars. Tapping the current star clears the rating.
const props = withDefaults(defineProps<{ value: number | null; size?: number; label?: string }>(), { size: 22 })
const emit = defineEmits<{ rate: [stars: number | null] }>()
const { t } = useI18n()
</script>

<template>
  <div class="flex items-center" role="group" :aria-label="label ?? t('common.rating')">
    <button
      v-for="n in 5"
      :key="n"
      type="button"
      class="grid place-items-center"
      :class="(value ?? 0) >= n ? 'text-accent' : 'text-line-strong'"
      :style="{ width: `${size + 10}px`, height: `${size + 18}px` }"
      :aria-label="value === n ? t('common.clearRating') : t('common.rateStars', { n })"
      :aria-pressed="value === n"
      @click="emit('rate', props.value === n ? null : n)"
    >
      <Star :size="size" :stroke-width="1.4" :fill="(value ?? 0) >= n ? 'currentColor' : 'none'" />
    </button>
  </div>
</template>
