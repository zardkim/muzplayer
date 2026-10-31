<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { THEMES, useUi } from '../stores/ui'

// colour themes, each with a small preview of its background, surface and accent
const SWATCHES = { default: ['#FFFFFF', '#F4F4F5', '#D93B22'], plexamp: ['#D3CDC7', '#F8F6F3', '#CC7B19'] }
const { t } = useI18n()
const ui = useUi()
</script>

<template>
  <div role="group" :aria-label="t('settings.theme')" class="flex flex-wrap gap-3">
    <button
      v-for="th in THEMES"
      :key="th"
      type="button"
      :aria-pressed="ui.theme === th"
      class="flex w-[150px] flex-col gap-2 rounded-2xl border p-2.5 text-left transition-colors"
      :class="ui.theme === th ? 'border-ink' : 'border-line-strong hover:border-ink'"
      @click="ui.theme = th"
    >
      <span class="flex h-16 overflow-hidden rounded-xl border border-line" :style="{ background: SWATCHES[th][0] }" aria-hidden="true">
        <span class="m-2 w-1/3 rounded-md" :style="{ background: SWATCHES[th][1] }" />
        <span class="m-2 ml-auto size-6 self-end rounded-full" :style="{ background: SWATCHES[th][2] }" />
      </span>
      <span class="px-1 text-[15px]" :class="ui.theme === th ? 'font-medium' : 'font-light'">{{ t(`settings.theme_${th}`) }}</span>
    </button>
  </div>
</template>
