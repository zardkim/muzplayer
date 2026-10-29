<script setup lang="ts">
import { computed, ref } from 'vue'

const props = withDefaults(
  defineProps<{ value: number; max: number; label: string; fill?: string; track?: string }>(),
  { fill: '', track: '' },
)
// `preview` fires while dragging (null when released); `change` once on release,
// so a drag doesn't trigger a burst of network seeks on mobile
const emit = defineEmits<{ change: [value: number]; preview: [value: number | null] }>()
const dragging = ref<number | null>(null)
const shown = computed(() => dragging.value ?? props.value)
const pct = computed(() => (props.max > 0 ? `${Math.min(100, (shown.value / props.max) * 100)}%` : '0%'))

function onInput(e: Event) {
  dragging.value = Number((e.target as HTMLInputElement).value)
  emit('preview', dragging.value)
}
function onChange(e: Event) {
  emit('change', Number((e.target as HTMLInputElement).value))
  dragging.value = null
  emit('preview', null)
}
</script>

<template>
  <input
    type="range"
    class="seek w-full"
    min="0"
    :max="max || 0"
    step="any"
    :value="shown"
    :aria-label="label"
    :style="{ '--pct': pct, ...(fill ? { '--fill': fill } : {}), ...(track ? { '--track': track } : {}) }"
    @input="onInput"
    @change="onChange"
  />
</template>
