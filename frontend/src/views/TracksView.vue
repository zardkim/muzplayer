<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ArrowDownUp } from '@lucide/vue'
import { api, query } from '../api'
import type { Genre, Page, Track } from '../types'
import LibraryHeader from '../components/LibraryHeader.vue'
import PageHeader from '../components/PageHeader.vue'
import PlayActions from '../components/PlayActions.vue'
import SelectPill from '../components/SelectPill.vue'
import TrackList from '../components/TrackList.vue'
import TrackTiles from '../components/TrackTiles.vue'
import ViewToggle from '../components/ViewToggle.vue'
import LoadMore from '../components/LoadMore.vue'
import { useUi } from '../stores/ui'
import { useListSearch } from '../listSearch'
import type { ViewMode } from '../types'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const ui = useUi()
const view = computed(() => (ui.views.tracks as ViewMode) || 'list')
const sort = computed(() => (typeof route.query.sort === 'string' ? route.query.sort : 'title'))
const genreId = typeof route.query.genre === 'string' ? Number(route.query.genre) : undefined
const genreName = ref('')
const items = ref<Track[]>([])
const total = ref(0)
const loading = ref(false)
const q = useListSearch(() => {
  items.value = []
  load()
})
let asked = 0

async function load() {
  const mine = ++asked
  loading.value = true
  try {
    const page = await api<Page<Track>>(`/tracks${query({ q: q.value.trim() || undefined, sort: sort.value, genre_id: genreId, limit: 200, offset: items.value.length })}`)
    if (mine !== asked) return
    items.value.push(...page.items)
    total.value = page.total
  } finally {
    if (mine === asked) loading.value = false
  }
}

onMounted(async () => {
  load()
  if (genreId) {
    const g = await api<{ items: Genre[] }>('/genres').catch(() => ({ items: [] }))
    genreName.value = g.items.find((x) => x.id === genreId)?.name ?? ''
  }
})

const sorts = [
  { key: 'title', label: 'tracks.sortTitle' },
  { key: 'artist', label: 'tracks.sortArtist' },
  { key: 'recent', label: 'tracks.sortRecent' },
]
</script>

<template>
  <div class="flex flex-col gap-5">
    <PageHeader v-if="genreId" :title="`#${genreName}`" :sub="t('common.tracks', total)" />
    <LibraryHeader v-else v-model:search="q" :search-label="t('tracks.search')" :sub="t('common.tracks', total)">
      <SelectPill :model-value="sort" :label="t('common.sort')" :icon="ArrowDownUp" :options="sorts.map((s) => ({ value: s.key, label: t(s.label) }))" @update:model-value="(s) => router.replace({ query: { ...route.query, sort: s } })" />
    </LibraryHeader>
    <div class="flex items-center gap-2">
    <!-- the buttons scroll in their own space; the view switch keeps its place beside them -->
    <div class="flex min-w-0 flex-1 gap-2 overflow-x-auto [scrollbar-width:none]">
      <PlayActions :tracks="items" :add="false" />
    </div>
    <ViewToggle page="tracks" fallback="list" class="flex-none" />
    </div>
    <p v-if="!loading && !items.length && q.trim()" class="font-light text-muted">{{ t('search.noResults') }}</p>
    <TrackList v-if="view === 'list'" :tracks="items" />
    <TrackTiles v-else :tracks="items" :dense="view === 'grid'" />
    <LoadMore v-if="items.length < total" auto :loading="loading" @click="load" />
  </div>
</template>
