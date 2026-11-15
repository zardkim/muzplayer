<script setup lang="ts">
import { isNew } from '../format'

// "NEW" on an album, chart or theme added in the last week, in the theme's own accent colour
defineProps<{ created?: string | null }>()
</script>

<template>
  <span
    v-if="isNew(created)"
    class="flex-none rounded bg-new px-1 text-[10px] font-bold leading-[16px] tracking-wide text-on-new"
  >NEW</span>
</template>
