<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { api, query } from '../api'
import type { Chart } from '../types'
import ChartGrid from '../components/ChartGrid.vue'
import PageHeader from '../components/PageHeader.vue'
import LoadMore from '../components/LoadMore.vue'
import ChoiceChip from '../components/ChoiceChip.vue'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const source = computed(() => (typeof route.query.source === 'string' ? route.query.source : ''))
const kind = computed(() => (route.query.kind === 'theme' ? 'theme' : 'chart'))
const items = ref<Chart[]>([])
const sources = ref<string[]>([])
const total = ref(0)
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    const page = await api<{ items: Chart[]; total: number; sources: string[] }>(
      `/charts${query({ kind: kind.value, source: source.value, limit: 120, offset: items.value.length })}`,
    )
    items.value.push(...page.items)
    total.value = page.total
    sources.value = page.sources
  } finally {
    loading.value = false
  }
}
onMounted(load)
</script>

<template>
  <div class="flex flex-col gap-6">
    <PageHeader :title="kind === 'theme' ? t('charts.themes') : t('charts.charts')" :sub="t(kind === 'theme' ? 'charts.themeCount' : 'charts.count', total)" />
    <div v-if="sources.length > 1" class="-mr-5 flex gap-2 overflow-x-auto pr-5 [scrollbar-width:none]">
      <ChoiceChip
        v-for="s in ['', ...sources]"
        :key="s"
        :active="source === s"
        @click="router.replace({ query: { kind: kind === 'theme' ? 'theme' : undefined, source: s || undefined } })"
      >
        {{ s || t('charts.all') }}
      </ChoiceChip>
    </div>
    <p v-if="!loading && !items.length" class="font-light text-muted">{{ t('charts.empty') }}</p>
    <ChartGrid :charts="items" />
    <LoadMore v-if="items.length < total" :loading="loading" @click="load" />
  </div>
</template>
