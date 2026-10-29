<script setup lang="ts">
import AccountMenu from './AccountMenu.vue'

// Large page title (mobile style). The ⋮ account menu shows on phones; desktop has it in the top bar.
defineProps<{ title: string; sub?: string }>()
</script>

<template>
  <div class="flex flex-col gap-1">
    <div class="flex items-center justify-between gap-3">
      <h1 class="min-w-0 text-[34px] font-extrabold leading-tight tracking-tight md:text-[40px]">{{ title }}</h1>
      <div class="flex items-center gap-1">
        <slot name="actions" />
        <AccountMenu class="md:hidden" />
      </div>
    </div>
    <p v-if="sub" class="text-[15px] font-light text-muted">{{ sub }}</p>
  </div>
</template>
