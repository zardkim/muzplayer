<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { X } from '@lucide/vue'

defineProps<{ title: string }>()
const emit = defineEmits<{ close: [] }>()
const { t } = useI18n()

function onKey(e: KeyboardEvent) {
  if (e.key === 'Escape') emit('close')
}
onMounted(() => window.addEventListener('keydown', onKey))
onUnmounted(() => window.removeEventListener('keydown', onKey))
</script>

<template>
  <div class="fixed inset-0 z-50 flex items-end justify-center bg-black/60 sm:items-center" @click.self="emit('close')">
    <div
      role="dialog"
      aria-modal="true"
      :aria-label="title"
      class="pb-safe max-h-[85vh] w-full overflow-y-auto rounded-t-2xl border border-line bg-surface p-5 sm:max-w-md sm:rounded-2xl"
    >
      <div class="mb-4 flex items-center justify-between">
        <h2 class="text-lg font-bold">{{ title }}</h2>
        <button type="button" class="grid size-11 place-items-center text-muted hover:text-ink" :aria-label="t('common.close')" @click="emit('close')">
          <X :size="20" />
        </button>
      </div>
      <slot />
    </div>
  </div>
</template>
