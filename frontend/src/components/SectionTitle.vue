<script setup lang="ts">
import type { RouteLocationRaw } from 'vue-router'
import { ChevronRight } from '@lucide/vue'

// A section's heading on the browsing pages; with `to`, it also opens the whole list (›).
defineProps<{ title: string; to?: RouteLocationRaw }>()
</script>

<template>
  <h2 class="text-[22px] font-bold">
    <RouterLink v-if="to" :to="to" class="inline-flex items-center gap-1">{{ title }}<ChevronRight :size="22" :stroke-width="1.6" aria-hidden="true" /></RouterLink>
    <template v-else>{{ title }}</template>
  </h2>
</template>
