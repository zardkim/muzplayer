<script setup lang="ts">
// Large page title (mobile style). The account menu is in the sidebar (PC) and the tab bar (phone).
defineProps<{ title: string; sub?: string }>()
</script>

<template>
  <div class="flex flex-col gap-1">
    <div class="flex items-center justify-between gap-3">
      <h1 class="min-w-0 text-[34px] font-extrabold leading-tight tracking-tight md:text-[40px]">{{ title }}</h1>
      <div class="flex items-center gap-1">
        <slot name="actions" />
      </div>
    </div>
    <p v-if="sub" class="text-[15px] font-light text-muted">{{ sub }}</p>
  </div>
</template>
