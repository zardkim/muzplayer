<script setup lang="ts">
defineProps<{ size?: number }>()
</script>

<template>
  <svg :width="size ?? 24" :height="size ?? 24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
    <path d="M4 6h16" /><path d="M4 12h10" /><path d="M4 18h8" /><path d="M16 15v6l5-3-5-3Z" />
  </svg>
</template>
