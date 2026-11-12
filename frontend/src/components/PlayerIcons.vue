<script setup lang="ts">
// Thin-stroke transport icons (play/pause/prev/next; rewind/forward: the radio tuner's seek) used by the player UIs.
defineProps<{ name: 'play' | 'pause' | 'prev' | 'next' | 'rewind' | 'forward'; size?: number; stroke?: number }>()
</script>

<template>
  <svg :width="size ?? 24" :height="size ?? 24" viewBox="0 0 24 24" fill="none" stroke="currentColor" :stroke-width="stroke ?? 1.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
    <path v-if="name === 'play'" d="M7 4.5v15l12-7.5-12-7.5Z" />
    <template v-else-if="name === 'pause'"><path d="M9 4.5v15" /><path d="M15 4.5v15" /></template>
    <template v-else-if="name === 'prev'"><path d="M19 5v14L8 12l11-7Z" /><path d="M5 5v14" /></template>
    <template v-else-if="name === 'rewind'"><path d="M12 6v12L3 12l9-6Z" fill="currentColor" /><path d="M21 6v12l-9-6 9-6Z" fill="currentColor" /></template>
    <template v-else-if="name === 'forward'"><path d="M12 6v12l9-6-9-6Z" fill="currentColor" /><path d="M3 6v12l9-6-9-6Z" fill="currentColor" /></template>
    <template v-else><path d="M5 5v14l11-7L5 5Z" /><path d="M19 5v14" /></template>
  </svg>
</template>
