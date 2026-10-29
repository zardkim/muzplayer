<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { LOCALES, setLocale } from '../i18n'

defineProps<{ compact?: boolean }>()
const { locale, t } = useI18n()
</script>

<template>
  <div
    role="group"
    :aria-label="t('settings.language')"
    class="inline-flex gap-1 rounded-full border border-line bg-surface p-1"
  >
    <button
      v-for="l in LOCALES"
      :key="l.code"
      type="button"
      :aria-pressed="locale === l.code"
      class="rounded-full font-medium transition-colors"
      :class="[
        compact ? 'px-3 py-1.5 text-[13px]' : 'px-4 py-2 text-sm',
        locale === l.code ? 'bg-ink text-bg' : 'text-muted hover:text-ink',
      ]"
      @click="setLocale(l.code)"
    >
      {{ l.label }}
    </button>
  </div>
</template>
