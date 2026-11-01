<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { Grid3x3, LayoutGrid, List } from '@lucide/vue'
import { useUi } from '../stores/ui'
import type { ViewMode } from '../types'

// List (목록형), covers (커버형: big artwork) or grid (격자형: small, dense artwork) for one page;
// remembered per page in this browser.
const props = defineProps<{ page: string; fallback: ViewMode; only?: ViewMode[] }>()
const { t } = useI18n()
const ui = useUi()
const mode = computed({
  get: () => (ui.views[props.page] as ViewMode) || props.fallback,
  set: (v: ViewMode) => (ui.views = { ...ui.views, [props.page]: v }),
})
const modes = [
  { key: 'list' as const, icon: List },
  { key: 'cover' as const, icon: LayoutGrid },
  { key: 'grid' as const, icon: Grid3x3 },
].filter((m) => !props.only || props.only.includes(m.key))
</script>

<template>
  <div class="flex flex-none items-center rounded-full bg-surface p-1" role="radiogroup" :aria-label="t('common.viewMode')">
    <button
      v-for="m in modes"
      :key="m.key"
      type="button"
      role="radio"
      class="grid size-8 place-items-center rounded-full transition-colors"
      :class="mode === m.key ? 'bg-bg text-ink shadow-sm' : 'text-muted hover:text-ink'"
      :aria-checked="mode === m.key"
      :aria-label="t(`common.view_${m.key}`)"
      :title="t(`common.view_${m.key}`)"
      @click="mode = m.key"
    >
      <component :is="m.icon" :size="16" :stroke-width="1.6" />
    </button>
  </div>
</template>
