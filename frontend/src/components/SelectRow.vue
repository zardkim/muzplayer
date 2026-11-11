<script setup lang="ts" generic="T extends string | number">
// one setting with a few choices: title and explanation on the left, a dropdown on the right
// (`disabled`: shown dimmed, when another setting makes it moot)
defineProps<{ title: string; hint?: string; options: { value: T; label: string }[]; disabled?: boolean }>()
const value = defineModel<T>({ required: true })
</script>

<template>
  <label class="flex items-center gap-4 py-3" :class="disabled ? 'opacity-50' : ''">
    <span class="flex min-w-0 flex-1 flex-col gap-0.5">
      <span class="text-[16px]">{{ title }}</span>
      <span v-if="hint" class="text-[13px] font-light text-muted">{{ hint }}</span>
    </span>
    <select v-model="value" :disabled="disabled" class="h-10 flex-none rounded-full border border-line-strong bg-bg px-3 text-sm">
      <option v-for="o in options" :key="String(o.value)" :value="o.value">{{ o.label }}</option>
    </select>
  </label>
</template>
