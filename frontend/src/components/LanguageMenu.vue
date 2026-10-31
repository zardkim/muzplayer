<script setup lang="ts">
import { onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Check, Globe } from '@lucide/vue'
import { LOCALES, setLocale, type Locale } from '../i18n'

// The language as a globe icon (login page): a tap opens the list, a tap on a language changes it.
const { locale, t } = useI18n()
const open = ref(false)
const box = ref<HTMLElement | null>(null)

function pick(code: Locale) {
  setLocale(code)
  open.value = false
}
function outside(e: Event) {
  if (box.value && !box.value.contains(e.target as Node)) open.value = false
}
function onKey(e: KeyboardEvent) {
  if (e.key === 'Escape') open.value = false
}
watch(open, (on) => {
  document[on ? 'addEventListener' : 'removeEventListener']('pointerdown', outside)
  document[on ? 'addEventListener' : 'removeEventListener']('keydown', onKey as EventListener)
})
onUnmounted(() => (open.value = false))
</script>

<template>
  <div ref="box" class="relative">
    <button
      type="button"
      class="flex h-10 items-center gap-1.5 rounded-full px-3 text-[14px] text-muted hover:bg-surface hover:text-ink"
      :aria-label="t('settings.language')"
      :aria-expanded="open"
      aria-haspopup="menu"
      @click="open = !open"
    >
      <Globe :size="20" :stroke-width="1.5" />
      <span class="font-display uppercase">{{ locale }}</span>
    </button>
    <div v-if="open" role="menu" class="absolute right-0 top-11 z-20 flex min-w-36 flex-col rounded-2xl border border-line bg-bg p-1.5 shadow-lg">
      <button
        v-for="l in LOCALES"
        :key="l.code"
        type="button"
        role="menuitemradio"
        :aria-checked="locale === l.code"
        class="flex h-10 items-center justify-between gap-3 rounded-xl px-3 text-left text-[15px] hover:bg-surface"
        @click="pick(l.code)"
      >
        {{ l.label }}<Check v-if="locale === l.code" :size="17" :stroke-width="1.8" class="text-accent" />
      </button>
    </div>
  </div>
</template>
