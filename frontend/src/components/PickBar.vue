<script setup lang="ts">
import { useI18n } from 'vue-i18n'

// While picking artists or genres to make one (admin): how many, cancel, and on to choosing the one to keep.
defineProps<{ count: number }>()
const emit = defineEmits<{ cancel: []; merge: [] }>()
const { t } = useI18n()
</script>

<template>
  <div class="sticky top-3 z-20 flex items-center gap-2 rounded-full border border-line bg-bg/95 py-1.5 pl-4 pr-1.5 shadow-sm backdrop-blur-sm">
    <span class="min-w-0 flex-1 truncate text-[14px]">{{ count ? t('merge.pickedCount', { n: count }) : t('merge.pickHint') }}</span>
    <button type="button" class="h-9 flex-none rounded-full px-3 text-[14px] text-muted hover:text-ink" @click="emit('cancel')">{{ t('common.cancel') }}</button>
    <button type="button" class="h-9 flex-none rounded-full bg-ink px-4 text-[14px] text-on-ink disabled:opacity-40" :disabled="count < 2" @click="emit('merge')">{{ t('merge.pickedMerge') }}</button>
  </div>
</template>
