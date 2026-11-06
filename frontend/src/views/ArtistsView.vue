<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ChevronRight } from '@lucide/vue'
import { api, query } from '../api'
import { useProgressive } from '../progressive'
import type { Artist, Page, ViewMode } from '../types'
import { useAuth } from '../stores/auth'
import ArtistPhoto from '../components/ArtistPhoto.vue'
import LibraryHeader from '../components/LibraryHeader.vue'
import MergeSheet from '../components/MergeSheet.vue'
import ViewToggle from '../components/ViewToggle.vue'
import LoadMore from '../components/LoadMore.vue'
import { useUi } from '../stores/ui'
import { useListSearch } from '../listSearch'

const { t } = useI18n()
const auth = useAuth()
const merging = ref(false) // admin: the duplicates sheet
const ui = useUi()
const view = computed(() => (ui.views.artists as ViewMode) || 'grid')
const items = ref<Artist[]>([])
const total = ref(0)
const loading = ref(false)
const shown = useProgressive(() => items.value)

const q = useListSearch(() => reload())
let asked = 0

async function load() {
  const mine = ++asked
  loading.value = true
  try {
    const page = await api<Page<Artist>>(`/artists${query({ q: q.value.trim() || undefined, limit: 200, offset: items.value.length })}`)
    if (mine !== asked) return
    items.value.push(...page.items)
    total.value = page.total
  } finally {
    if (mine === asked) loading.value = false
  }
}
onMounted(load)
function reload() {
  items.value = []
  void load()
}
</script>

<template>
  <div class="flex flex-col gap-5">
    <LibraryHeader v-model:search="q" :search-label="t('artists.search')" :sub="t('artists.count', total)">
      <div class="flex items-center gap-2">
        <button v-if="auth.user?.is_admin" type="button" class="h-8 flex-none rounded-full border border-line-strong px-3 text-[13px] hover:border-ink" @click="merging = true">{{ t('merge.open') }}</button>
        <ViewToggle page="artists" fallback="grid" />
      </div>
    </LibraryHeader>
    <p v-if="!loading && !items.length && q.trim()" class="font-light text-muted">{{ t('search.noResults') }}</p>
    <ul
      v-if="view !== 'list'"
      class="grid gap-x-4 gap-y-6"
      :class="view === 'grid' ? 'grid-cols-3 sm:grid-cols-[repeat(auto-fill,minmax(130px,1fr))]' : 'grid-cols-2 sm:grid-cols-[repeat(auto-fill,minmax(200px,1fr))] sm:gap-x-6'"
    >
      <li v-for="a in shown" :key="a.id">
        <RouterLink :to="{ name: 'artist', params: { id: a.id } }" class="group flex flex-col items-center gap-2.5 text-center">
          <ArtistPhoto :artist-id="a.id" :name="a.name" :version="a.image_v" :size="view === 'cover' ? 'large' : 'thumb'" class="w-full transition-transform duration-200 group-hover:scale-[1.03]" />
          <span class="flex w-full min-w-0 flex-col">
            <span class="truncate" :class="view === 'cover' ? 'text-[17px] font-medium' : 'text-[15px]'">{{ a.name }}</span>
            <span class="truncate text-[13px] font-light text-muted">{{ t('common.tracks', a.track_count) }}</span>
          </span>
        </RouterLink>
      </li>
    </ul>
    <ul v-else class="grid grid-cols-1 gap-x-8 sm:grid-cols-2 xl:grid-cols-3">
      <li v-for="a in shown" :key="a.id">
        <RouterLink :to="{ name: 'artist', params: { id: a.id } }" class="flex min-h-[64px] items-center gap-3.5 border-b border-surface">
          <ArtistPhoto :artist-id="a.id" :name="a.name" :version="a.image_v" class="size-11 flex-none" />
          <span class="flex min-w-0 flex-1 flex-col">
            <span class="truncate text-[17px]">{{ a.name }}</span>
            <span class="text-sm font-light text-muted"><template v-if="a.album_count">{{ t('common.albums', a.album_count) }} · </template>{{ t('common.tracks', a.track_count) }}</span>
          </span>
          <ChevronRight :size="18" class="text-subtle" />
        </RouterLink>
      </li>
    </ul>
    <MergeSheet v-if="merging" kind="artist" @close="merging = false" @changed="reload" />
    <LoadMore v-if="items.length < total" auto :loading="loading" @click="load" />
  </div>
</template>
