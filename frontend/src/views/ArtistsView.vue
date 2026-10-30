<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ChevronRight } from '@lucide/vue'
import { api, query } from '../api'
import type { Artist, Page, ViewMode } from '../types'
import ArtistPhoto from '../components/ArtistPhoto.vue'
import LibraryHeader from '../components/LibraryHeader.vue'
import ViewToggle from '../components/ViewToggle.vue'
import { useUi } from '../stores/ui'

const { t } = useI18n()
const ui = useUi()
const view = computed(() => (ui.views.artists as ViewMode) || 'grid')
const items = ref<Artist[]>([])
const total = ref(0)
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    const page = await api<Page<Artist>>(`/artists${query({ limit: 500, offset: items.value.length })}`)
    items.value.push(...page.items)
    total.value = page.total
  } finally {
    loading.value = false
  }
}
onMounted(load)
</script>

<template>
  <div class="flex flex-col gap-5">
    <LibraryHeader :sub="t('artists.count', total)">
      <ViewToggle page="artists" fallback="grid" />
    </LibraryHeader>
    <ul
      v-if="view !== 'list'"
      class="grid gap-x-4 gap-y-6"
      :class="view === 'grid' ? 'grid-cols-3 sm:grid-cols-[repeat(auto-fill,minmax(130px,1fr))]' : 'grid-cols-2 sm:grid-cols-[repeat(auto-fill,minmax(200px,1fr))] sm:gap-x-6'"
    >
      <li v-for="a in items" :key="a.id">
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
      <li v-for="a in items" :key="a.id">
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
    <button v-if="items.length < total" type="button" class="mx-auto h-11 rounded-full border border-line-strong px-6 text-[15px]" :disabled="loading" @click="load">
      {{ loading ? t('common.loading') : t('common.loadMore') }}
    </button>
  </div>
</template>
