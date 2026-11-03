<script setup lang="ts">
// One of a row of choices (a kind, a tab, a source): filled when it is the one picked.
// `tab`: part of a tablist (aria-selected rather than aria-pressed); `small`: inside a sheet.
defineProps<{ active: boolean; tab?: boolean; small?: boolean }>()
</script>

<template>
  <button
    type="button"
    :role="tab ? 'tab' : undefined"
    :aria-selected="tab ? active : undefined"
    :aria-pressed="tab ? undefined : active"
    class="flex-none rounded-full border"
    :class="[small ? 'h-9 px-3.5 text-[14px]' : 'h-[38px] px-4 text-[15px]', active ? 'border-ink bg-ink text-on-ink' : 'border-line-strong bg-bg']"
  >
    <slot />
  </button>
</template>
