<script setup lang="ts">
import { computed, onActivated, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { api, query } from '../api'
import type { Album, Page } from '../types'
import AlbumGrid from '../components/AlbumGrid.vue'
import LibraryHeader from '../components/LibraryHeader.vue'
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
    <LibraryHeader :sub="t('albums.count', total)" />
    <div class="flex flex-col gap-2.5">
      <div class="-mr-5 flex gap-2 overflow-x-auto pr-5 [scrollbar-width:none]">
        <button
          v-for="k in kinds"
          :key="k.key"
          type="button"
          class="h-[38px] flex-none rounded-full border px-4 text-[15px]"
          :class="kind === k.key ? 'border-ink bg-ink text-on-ink' : 'border-line-strong bg-bg'"
          @click="router.replace({ query: { ...route.query, kind: k.key || undefined } })"
        >
          {{ t(k.label) }}
        </button>
      </div>
      <!-- the sorts scroll in their own space; the view switch keeps its place beside them -->
      <div class="flex items-center gap-2">
      <div class="flex min-w-0 flex-1 gap-1 overflow-x-auto text-[14px] [scrollbar-width:none]">
        <button
          v-for="s in sorts"
          :key="s.key"
          type="button"
          class="h-8 flex-none rounded-full px-3"
          :class="sort === s.key ? 'bg-surface-2 font-medium' : 'font-light text-muted'"
          @click="router.replace({ query: { ...route.query, sort: s.key } })"
        >
          {{ t(s.label) }}
        </button>
      </div>
      <ViewToggle page="albums" fallback="cover" class="ml-auto flex-none" />
      </div>
    </div>
    <p v-if="!loading && !items.length" class="font-light text-muted">{{ t('albums.empty') }}</p>
    <AlbumGrid :albums="items" :mode="view" />
    <button v-if="items.length < total" type="button" class="mx-auto h-11 rounded-full border border-line-strong px-6 text-[15px]" :disabled="loading" @click="load">
      {{ loading ? t('common.loading') : t('common.loadMore') }}
    </button>
  </div>
</template>
