<script setup lang="ts">
import { ChevronRight } from '@lucide/vue'

// A row to pick in a sheet (an album, an artist...): its picture (slot), name and a line under it, ›.
defineProps<{ title: string; sub?: string }>()
</script>

<template>
  <button type="button" class="flex w-full items-center gap-3 rounded-xl px-2 py-1.5 text-left hover:bg-surface">
    <slot />
    <span class="flex min-w-0 flex-1 flex-col">
      <span class="truncate text-[15px]">{{ title }}</span>
      <span v-if="sub" class="truncate text-[13px] text-muted">{{ sub }}</span>
    </span>
    <ChevronRight :size="18" class="flex-none text-subtle" aria-hidden="true" />
  </button>
</template>
