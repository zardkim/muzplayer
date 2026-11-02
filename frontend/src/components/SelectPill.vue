<script setup lang="ts" generic="V extends string | null">
import type { Component } from 'vue'
import { ChevronDown } from '@lucide/vue'

// A drop-down as a pill: the page's kind or order (videos, radio, albums, songs, genres). The
// device's own picker opens, so a phone gets its native list.
defineProps<{ label: string; icon: Component; options: { value: V; label: string }[] }>()
const model = defineModel<V>({ required: true })
</script>

<template>
  <span class="relative flex h-[38px] flex-none items-center rounded-full border border-line-strong bg-bg focus-within:ring-2 focus-within:ring-ink">
    <component :is="icon" :size="15" :stroke-width="1.6" class="pointer-events-none absolute left-3.5 text-muted" aria-hidden="true" />
    <select v-model="model" :aria-label="label" :title="label" class="h-full cursor-pointer appearance-none rounded-full bg-transparent pl-9 pr-8 text-[15px] outline-none">
      <option v-for="o in options" :key="o.value ?? ''" :value="o.value">{{ o.label }}</option>
    </select>
    <ChevronDown :size="15" :stroke-width="1.8" class="pointer-events-none absolute right-3 text-muted" aria-hidden="true" />
  </span>
</template>
