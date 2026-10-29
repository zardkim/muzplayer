<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { LOCALES, setLocale } from '../i18n'

defineProps<{ compact?: boolean }>()
const { locale, t } = useI18n()
</script>

<template>
  <div role="group" :aria-label="t('settings.language')" class="inline-flex gap-1.5">
    <button
      v-for="l in LOCALES"
      :key="l.code"
      type="button"
      :aria-pressed="locale === l.code"
      class="rounded-full border transition-colors"
      :class="[
        compact ? 'h-8 px-3 text-[13px]' : 'h-10 px-4 text-[15px]',
        locale === l.code ? 'border-ink bg-ink text-white' : 'border-line-strong bg-bg text-ink hover:border-ink',
      ]"
      @click="setLocale(l.code)"
    >
      {{ l.label }}
    </button>
  </div>
</template>
