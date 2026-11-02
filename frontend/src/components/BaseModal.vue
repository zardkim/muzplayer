<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { X } from '@lucide/vue'
import { useSwipe } from '../swipe'

// wide: a bigger dialog on a PC (video search and lists); video: bigger still (watching videos)
defineProps<{ title: string; wide?: boolean; video?: boolean }>()
const emit = defineEmits<{ close: [] }>()
const { t } = useI18n()

// closed from here (✕, outside it, Esc): it goes down (or fades on a PC) before it is gone
const leaving = ref(false)
function close() {
  if (leaving.value) return
  leaving.value = true
  window.setTimeout(() => emit('close'), 260)
}
function onKey(e: KeyboardEvent) {
  if (e.key === 'Escape') close()
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
    const away = dy > 120 || (fast && dy > 40)
    pulled.value = away ? window.innerHeight : 0
    window.setTimeout(() => {
      settling.value = false
      if (away) emit('close') // (it stays down while it goes)
    }, 300)
  },
})

onMounted(() => window.addEventListener('keydown', onKey))
onUnmounted(() => window.removeEventListener('keydown', onKey))
</script>

<template>
  <div
    class="modal-backdrop fixed inset-0 z-[70] flex items-end justify-center bg-black/30 sm:items-center"
    :class="[leaving ? 'modal-leaving' : '', settling ? 'transition-colors duration-300' : '']"
    :style="pulled ? { backgroundColor: `rgb(0 0 0 / ${Math.max(0, 0.3 * (1 - pulled / 500))})` } : undefined"
    @click.self="close"
  >
    <div
      ref="sheet"
      role="dialog"
      aria-modal="true"
      :aria-label="title"
      class="modal-sheet w-full overflow-y-auto rounded-t-3xl bg-bg p-5 pb-[calc(1.5rem+env(safe-area-inset-bottom))] shadow-2xl sm:rounded-3xl sm:pb-6"
      :class="[video ? 'max-h-[92vh] sm:max-h-[94vh] sm:max-w-6xl sm:p-7 sm:pb-8' : wide ? 'max-h-[85vh] sm:max-h-[90vh] sm:max-w-3xl sm:p-7 sm:pb-8' : 'max-h-[85vh] sm:max-w-md', settling ? 'transition-transform duration-300 ease-[cubic-bezier(0.2,0.9,0.3,1)]' : '']"
      :style="pulled ? { transform: `translate3d(0,${pulled}px,0)` } : undefined"
      @touchstart="pull.onTouchstart"
      @touchmove="pull.onTouchmove"
      @touchend="pull.onTouchend"
      @touchcancel="pull.onTouchcancel"
    >
      <!-- the grab handle of a phone sheet -->
      <div class="-mt-2 mb-2 flex justify-center sm:hidden" aria-hidden="true"><span class="h-1 w-10 rounded-full bg-line-strong" /></div>
      <div class="mb-4 flex items-center justify-between">
        <h2 class="text-xl font-bold">{{ title }}</h2>
        <button type="button" class="grid size-11 place-items-center text-ink" :aria-label="t('common.close')" @click="close">
          <X :size="22" :stroke-width="1.4" />
        </button>
      </div>
      <slot />
    </div>
  </div>
</template>
