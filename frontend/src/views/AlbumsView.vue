<script setup lang="ts">
import { computed, onActivated, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ArrowDownUp, LayoutGrid } from '@lucide/vue'
import { api, query } from '../api'
import type { Album, Page } from '../types'
import AlbumGrid from '../components/AlbumGrid.vue'
import LibraryHeader from '../components/LibraryHeader.vue'
import SelectPill from '../components/SelectPill.vue'
import ViewToggle from '../components/ViewToggle.vue'
import { useUi } from '../stores/ui'
import type { ViewMode } from '../types'

const { t } = useI18n()
const route = useRoute()
const ui = useUi()
const view = computed(() => (ui.views.albums as ViewMode) || 'cover')
const router = useRouter()
const sort = computed(() => (typeof route.query.sort === 'string' ? route.query.sort : 'recent'))
const kind = computed(() => (typeof route.query.kind === 'string' ? route.query.kind : ''))
const items = ref<Album[]>([])
const total = ref(0)
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    const page = await api<Page<Album>>(`/albums${query({ sort: sort.value, kind: kind.value, limit: 120, offset: items.value.length })}`)
    items.value.push(...page.items)
    total.value = page.total
  } finally {
    loading.value = false
  }
}
onMounted(load)
// "my rating" changes as albums are rated elsewhere; the kept page reloads that order
onActivated(() => {
  if (sort.value === 'rating' && !loading.value) {
    items.value = []
    load()
  }
})

const kinds = [
  { key: '', label: 'albums.kindAll' },
  { key: 'album', label: 'albums.kind_album' },
  { key: 'unofficial', label: 'albums.kind_unofficial' },
  { key: 'compilation', label: 'albums.kind_compilation' },
  { key: 'soundtrack', label: 'albums.kind_soundtrack' },
]
const sorts = [
  { key: 'recent', label: 'albums.sortRecent' },
  { key: 'title', label: 'albums.sortTitle' },
  { key: 'rating', label: 'albums.sortRating' },
  { key: 'artist', label: 'albums.sortArtist' },
  { key: 'year', label: 'albums.sortYear' },
]
</script>

<template>
  <div class="flex flex-col gap-6">
    <LibraryHeader :sub="t('albums.count', total)">
      <ViewToggle page="albums" fallback="cover" />
    </LibraryHeader>
    <div class="flex flex-wrap items-center gap-2">
      <SelectPill :model-value="kind" :label="t('common.kind')" :icon="LayoutGrid" :options="kinds.map((k) => ({ value: k.key, label: t(k.label) }))" @update:model-value="(k) => router.replace({ query: { ...route.query, kind: k || undefined } })" />
      <SelectPill :model-value="sort" :label="t('common.sort')" :icon="ArrowDownUp" :options="sorts.map((s) => ({ value: s.key, label: t(s.label) }))" @update:model-value="(s) => router.replace({ query: { ...route.query, sort: s } })" />
    </div>
    <p v-if="!loading && !items.length" class="font-light text-muted">{{ t('albums.empty') }}</p>
    <AlbumGrid :albums="items" :mode="view" />
    <button v-if="items.length < total" type="button" class="mx-auto h-11 rounded-full border border-line-strong px-6 text-[15px]" :disabled="loading" @click="load">
      {{ loading ? t('common.loading') : t('common.loadMore') }}
    </button>
  </div>
</template>
