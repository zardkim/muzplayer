<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { artistImageUrl } from '../api'

// An artist's photo, round by default; without one, the first letter on a colour taken from the name
// (the same artist always gets the same colour).
const props = withDefaults(
  defineProps<{ artistId: number; name: string; version: number; size?: 'thumb' | 'large'; rounded?: string }>(),
  { size: 'thumb', rounded: 'rounded-full' },
)
const failed = ref(false)
watch(() => [props.artistId, props.version], () => (failed.value = false))

const PALETTE = ['#3D5A80', '#2F7D6D', '#6B5B95', '#8A6516', '#A34A6E', '#4A6FA5', '#7A5C3E', '#2E6F8E']
const tint = computed(() => {
  let h = 0
  for (const ch of props.name) h = (h * 31 + ch.charCodeAt(0)) >>> 0
  return PALETTE[h % PALETTE.length]
})
</script>

<template>
  <span class="relative block aspect-square overflow-hidden" :class="rounded">
    <img
      v-if="version && !failed"
      :src="artistImageUrl(artistId, size, version)"
      alt=""
      loading="lazy"
      decoding="async"
      class="h-full w-full object-cover"
      @error="failed = true"
    />
    <span v-else class="grid h-full w-full place-items-center font-medium text-white [container-type:inline-size]" :style="{ background: tint }">
      <span class="text-[40cqw] leading-none">{{ name.slice(0, 1).toUpperCase() }}</span>
    </span>
  </span>
</template>
