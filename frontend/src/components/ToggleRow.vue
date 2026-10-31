<script setup lang="ts">
// one setting: title and a line of explanation on the left, an on/off switch on the right
defineProps<{ title: string; hint?: string; disabled?: boolean }>()
const on = defineModel<boolean>({ required: true })
</script>

<template>
  <label class="flex cursor-pointer items-center gap-4 py-3" :class="disabled ? 'cursor-default opacity-50' : ''">
    <span class="flex min-w-0 flex-1 flex-col gap-0.5">
      <span class="text-[16px]">{{ title }}</span>
      <span v-if="hint" class="text-[13px] font-light text-muted">{{ hint }}</span>
    </span>
    <input v-model="on" type="checkbox" role="switch" class="peer sr-only" :disabled="disabled" />
    <span
      class="relative h-7 w-12 flex-none rounded-full transition-colors peer-focus-visible:ring-2 peer-focus-visible:ring-ink"
      :class="on ? 'bg-accent' : 'bg-line-strong'"
      aria-hidden="true"
    >
      <span class="absolute top-0.5 size-6 rounded-full bg-white shadow transition-[left]" :class="on ? 'left-[22px]' : 'left-0.5'" />
    </span>
  </label>
</template>
