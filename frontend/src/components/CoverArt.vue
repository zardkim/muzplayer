<script setup lang="ts">
import { ref, watch } from 'vue'
import { coverUrl } from '../api'

const props = withDefaults(
  defineProps<{ albumId: number | null; hasCover: boolean; version?: number; size?: 'thumb' | 'large'; rounded?: string }>(),
  { size: 'thumb', rounded: 'rounded-lg' },
)
const failed = ref(false)
watch(() => props.albumId, () => (failed.value = false))
</script>

<template>
  <div class="relative aspect-square overflow-hidden bg-surface" :class="rounded">
    <img
      v-if="albumId && hasCover && !failed"
      :src="coverUrl(albumId, size, version)"
      alt=""
      loading="lazy"
      decoding="async"
      class="h-full w-full object-cover"
      @error="failed = true"
    />
    <!-- drawn inline in theme colours (the dark theme would otherwise show light squares) -->
    <svg v-else viewBox="0 0 300 300" class="h-full w-full" aria-hidden="true">
      <rect width="300" height="300" class="fill-surface" />
      <circle cx="150" cy="150" r="70" class="fill-line" />
      <circle cx="150" cy="150" r="56" fill="none" stroke-width="3" class="stroke-surface" />
      <circle cx="150" cy="150" r="14" class="fill-surface" />
    </svg>
    <slot />
  </div>
</template>
