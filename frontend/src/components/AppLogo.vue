<script setup lang="ts">
withDefaults(defineProps<{ size?: number; wordmark?: boolean }>(), { size: 32, wordmark: true })
</script>

<template>
  <span class="inline-flex items-center gap-2.5">
    <svg :width="size" :height="size" viewBox="0 0 64 64" aria-hidden="true">
      <circle cx="32" cy="32" r="30" fill="#F5A524" />
      <circle v-if="size >= 48" cx="32" cy="32" r="24.5" fill="none" stroke="#0E1013" stroke-width="1.5" opacity="0.55" />
      <circle cx="32" cy="32" r="19" fill="#0E1013" />
      <path d="M27.5 24 L41 32 L27.5 40 Z" fill="#F5A524" stroke="#F5A524" stroke-width="3" stroke-linejoin="round" />
    </svg>
    <span v-if="wordmark" class="font-display tracking-tight" :style="{ fontSize: `${Math.round(size * 0.68)}px` }">
      <b>muz</b><span class="text-muted">player</span>
    </span>
  </span>
</template>
