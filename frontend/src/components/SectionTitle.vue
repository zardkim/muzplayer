<script setup lang="ts">
import type { RouteLocationRaw } from 'vue-router'
import { ChevronRight } from '@lucide/vue'
import SourceLogo from './SourceLogo.vue'

// A section's heading on the browsing pages; with `to`, it also opens the whole list (›). `count`: how many, small beside it.
// `source`: a chart site's logo before it.
defineProps<{ title: string; to?: RouteLocationRaw; count?: number; source?: string }>()
</script>

<template>
  <h2 class="text-[22px] font-bold">
    <RouterLink v-if="to" :to="to" class="inline-flex items-center gap-1"><SourceLogo v-if="source" :source="source" :size="24" class="mr-1" />{{ title }}<span v-if="count" class="text-[15px] font-normal text-muted">{{ count }}</span><ChevronRight :size="22" :stroke-width="1.6" aria-hidden="true" /></RouterLink>
    <template v-else><SourceLogo v-if="source" :source="source" :size="24" class="mr-2 inline-block align-[-3px]" />{{ title }}<span v-if="count" class="ml-1 text-[15px] font-normal text-muted">{{ count }}</span></template>
  </h2>
</template>
