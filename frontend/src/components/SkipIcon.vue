<script setup lang="ts">
// Circular arrow with the number of seconds inside, for the audiobook skip buttons.
defineProps<{ seconds: number; forward?: boolean; size?: number }>()
</script>

<template>
  <span class="relative inline-grid place-items-center" :style="{ width: `${size ?? 32}px`, height: `${size ?? 32}px` }">
    <svg :width="size ?? 32" :height="size ?? 32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" :style="forward ? 'transform: scaleX(-1)' : ''">
      <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" /><path d="M3 3v5h5" />
    </svg>
    <span class="absolute font-display font-semibold leading-none" :style="{ fontSize: `${Math.round((size ?? 32) * 0.3)}px` }" aria-hidden="true">{{ seconds }}</span>
  </span>
</template>
