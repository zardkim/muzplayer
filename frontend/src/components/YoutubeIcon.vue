<script setup lang="ts">
// YouTube's play-button mark (a song with videos added; tapping it plays one)
withDefaults(defineProps<{ size?: number }>(), { size: 20 })
</script>

<template>
  <svg :width="size" :height="size * 0.72" viewBox="0 0 28 20" aria-hidden="true">
    <rect width="28" height="20" rx="5.5" fill="#ff0000" />
    <path d="M11.2 5.7v8.6l7.4-4.3z" fill="#fff" />
  </svg>
</template>
