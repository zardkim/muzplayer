<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { X } from '@lucide/vue'
import { useSwipe } from '../swipe'

// wide: a bigger dialog on a PC (video search and lists); video: bigger still (watching videos)
defineProps<{ title: string; wide?: boolean; video?: boolean }>()
const emit = defineEmits<{ close: [] }>()
const { t } = useI18n()

function onKey(e: KeyboardEvent) {
  if (e.key === 'Escape') emit('close')
}
// phones (a sheet from the bottom): pull it down to close, once its content is scrolled to the top
const sheet = ref<HTMLElement | null>(null)
const pulled = ref(0)
const settling = ref(false)
const pull = useSwipe({
  axes: ['y'],
  allow: (_, __, dy) => dy > 0 && (sheet.value?.scrollTop ?? 0) <= 0 && window.innerWidth < 640,
  move: (_, __, dy) => (pulled.value = Math.max(0, dy)),
  end: ({ dy, fast }) => {
    settling.value = true
    const close = dy > 120 || (fast && dy > 40)
    pulled.value = close ? window.innerHeight : 0
    window.setTimeout(() => {
      settling.value = false
      if (close) emit('close')
      pulled.value = 0
    }, 200)
  },
})

onMounted(() => window.addEventListener('keydown', onKey))
onUnmounted(() => window.removeEventListener('keydown', onKey))
</script>

<template>
  <div class="fixed inset-0 z-[70] flex items-end justify-center bg-black/30 sm:items-center" @click.self="emit('close')">
    <div
      ref="sheet"
      role="dialog"
      aria-modal="true"
      :aria-label="title"
      class="w-full overflow-y-auto rounded-t-3xl bg-bg p-5 pb-[calc(1.5rem+env(safe-area-inset-bottom))] shadow-2xl sm:rounded-3xl sm:pb-6"
      :class="[video ? 'max-h-[92vh] sm:max-h-[94vh] sm:max-w-6xl sm:p-7 sm:pb-8' : wide ? 'max-h-[85vh] sm:max-h-[90vh] sm:max-w-3xl sm:p-7 sm:pb-8' : 'max-h-[85vh] sm:max-w-md', settling ? 'transition-transform duration-200 ease-out' : '']"
      :style="pulled ? { transform: `translateY(${pulled}px)` } : undefined"
      @touchstart="pull.onTouchstart"
      @touchmove="pull.onTouchmove"
      @touchend="pull.onTouchend"
      @touchcancel="pull.onTouchcancel"
    >
      <!-- the grab handle of a phone sheet -->
      <div class="-mt-2 mb-2 flex justify-center sm:hidden" aria-hidden="true"><span class="h-1 w-10 rounded-full bg-line-strong" /></div>
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
