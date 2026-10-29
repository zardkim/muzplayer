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
  <div class="fixed inset-0 z-[70] flex items-end justify-center bg-black/30 sm:items-center" @click.self="emit('close')">
    <div
      role="dialog"
      aria-modal="true"
      :aria-label="title"
      class="pb-safe max-h-[85vh] w-full overflow-y-auto rounded-t-3xl bg-bg p-5 shadow-2xl sm:max-w-md sm:rounded-3xl"
    >
      <div class="mb-4 flex items-center justify-between">
        <h2 class="text-xl font-bold">{{ title }}</h2>
        <button type="button" class="grid size-11 place-items-center text-ink" :aria-label="t('common.close')" @click="emit('close')">
          <X :size="22" :stroke-width="1.4" />
        </button>
      </div>
      <slot />
    </div>
  </div>
</template>
