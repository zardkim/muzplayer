<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{ value: number; max: number; label: string; fill?: string }>(), { fill: '' })
const emit = defineEmits<{ change: [value: number] }>()
const pct = computed(() => (props.max > 0 ? `${Math.min(100, (props.value / props.max) * 100)}%` : '0%'))
</script>

<template>
  <input
    type="range"
    class="seek w-full"
    min="0"
    :max="max || 0"
    step="any"
    :value="value"
    :aria-label="label"
    :style="{ '--pct': pct, ...(fill ? { '--fill': fill } : {}) }"
    @input="emit('change', Number(($event.target as HTMLInputElement).value))"
  />
</template>
