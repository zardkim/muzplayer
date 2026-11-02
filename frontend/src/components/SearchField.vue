<script setup lang="ts">
import { Search } from '@lucide/vue'

// A list page's own search box (music videos, the library's tabs): it narrows what that page shows.
defineProps<{ placeholder: string }>()
const model = defineModel<string>({ required: true })
</script>

<template>
  <label class="flex h-[38px] min-w-0 items-center gap-2 rounded-full bg-surface px-4 focus-within:ring-2 focus-within:ring-ink">
    <Search :size="16" :stroke-width="1.5" class="flex-none text-muted" aria-hidden="true" />
    <span class="sr-only">{{ placeholder }}</span>
    <input v-model="model" type="search" maxlength="200" :placeholder="placeholder" enterkeyhint="search" class="min-w-0 flex-1 bg-transparent text-[15px] outline-none" />
  </label>
</template>
