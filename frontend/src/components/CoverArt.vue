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
      class="h-full w-full object-cover"
      @error="failed = true"
    />
    <img v-else src="/cover-placeholder.svg" alt="" class="h-full w-full object-cover" />
    <slot />
  </div>
</template>
