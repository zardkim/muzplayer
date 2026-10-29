<script setup lang="ts">
import { ref, watch } from 'vue'
import { Headphones } from '@lucide/vue'
import { bookCoverUrl } from '../api'

// Audiobook covers are usually 2:3 portraits: shown whole in a 2:3 box. `square` (small
// round thumbnails in the player bars) crops instead, as a letterboxed sliver reads badly
const props = withDefaults(
  defineProps<{ bookId: number | null; hasCover: boolean; size?: 'thumb' | 'large'; rounded?: string; square?: boolean }>(),
  { size: 'thumb', rounded: 'rounded-lg' },
)
const failed = ref(false)
watch(() => props.bookId, () => (failed.value = false))
</script>

<template>
  <div class="relative overflow-hidden bg-surface" :class="[rounded, square ? 'aspect-square' : 'aspect-[2/3]']">
    <img
      v-if="bookId && hasCover && !failed"
      :src="bookCoverUrl(bookId, size)"
      alt=""
      loading="lazy"
      class="h-full w-full"
      :class="square ? 'object-cover' : 'object-contain'"
      @error="failed = true"
    />
    <span v-else class="grid h-full w-full place-items-center text-subtle"><Headphones :size="square ? 18 : 36" :stroke-width="1.2" /></span>
    <slot />
  </div>
</template>
