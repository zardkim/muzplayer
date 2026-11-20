<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { ExternalLink } from '@lucide/vue'
import BaseModal from './BaseModal.vue'
import ChoiceChip from './ChoiceChip.vue'

// The details of a song or a video (their ⋮ menu's "info"), a tab per part. A phone: a sheet from the
// bottom, each label over its value; a PC: a wider dialog, labels in a column beside the values, a long
// tab scrolling inside it. A value can lead somewhere: in the app (to) or out of it (href).
export interface InfoRow {
  label: string
  value: string
  to?: string
  href?: string
}
export interface InfoTab {
  key: string
  label: string
  rows: InfoRow[]
}
const props = defineProps<{ title: string; subtitle?: string; tabs: InfoTab[]; error?: string }>()
const emit = defineEmits<{ close: [] }>()
const { t } = useI18n()
const tab = ref(props.tabs[0]?.key ?? '')
watch(() => props.tabs, (tabs) => {
  if (!tabs.some((x) => x.key === tab.value)) tab.value = tabs[0]?.key ?? ''
})
</script>

<template>
  <BaseModal :title="title" wide @close="emit('close')">
    <div class="flex flex-col gap-4">
      <p v-if="subtitle" class="-mt-2 truncate text-[15px] font-medium">{{ subtitle }}</p>
      <p v-if="error" class="text-[14px] text-danger" role="alert">{{ error }}</p>
      <template v-else-if="tabs.length">
        <div class="flex gap-2 overflow-x-auto [scrollbar-width:none]" role="tablist">
          <ChoiceChip v-for="x in tabs" :key="x.key" tab small :active="tab === x.key" @click="tab = x.key">{{ x.label }}</ChoiceChip>
        </div>
        <template v-for="x in tabs" :key="x.key">
          <dl
            v-if="tab === x.key"
            role="tabpanel"
            class="flex flex-col gap-3 rounded-2xl bg-surface px-4 py-3.5 text-[14px] md:grid md:max-h-[58vh] md:grid-cols-[150px_minmax(0,1fr)] md:gap-x-5 md:gap-y-2 md:overflow-y-auto md:px-5 md:py-4"
          >
            <div v-for="(r, i) in x.rows" :key="`${r.label}-${i}`" class="flex min-w-0 flex-col gap-0.5 md:contents">
              <dt class="text-[12px] text-muted md:text-[14px]">{{ r.label }}</dt>
              <dd class="min-w-0 select-text break-all">
                <RouterLink v-if="r.to" :to="r.to" class="underline decoration-line-strong underline-offset-2 hover:decoration-ink" @click="emit('close')">{{ r.value }}</RouterLink>
                <a v-else-if="r.href" :href="r.href" target="_blank" rel="noopener" class="inline-flex items-center gap-1 underline decoration-line-strong underline-offset-2 hover:decoration-ink">{{ r.value }}<ExternalLink :size="13" class="flex-none" /></a>
                <template v-else>{{ r.value }}</template>
              </dd>
            </div>
            <p v-if="!x.rows.length" class="text-muted md:col-span-2">{{ t('trackInfo.none') }}</p>
          </dl>
        </template>
      </template>
      <p v-else class="text-[14px] text-muted">…</p>
    </div>
  </BaseModal>
</template>
