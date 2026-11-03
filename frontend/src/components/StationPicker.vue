<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { ChevronRight, Search } from '@lucide/vue'
import { api, query } from '../api'
import type { Album, Artist, Genre, Page } from '../types'
import ArtistPhoto from './ArtistPhoto.vue'
import BaseModal from './BaseModal.vue'
import CoverArt from './CoverArt.vue'

// What a station plays from (home → stations): an artist or an album (searched), a genre, a decade.
const props = defineProps<{ kind: 'artist' | 'album' | 'genre' | 'decade' }>()
const emit = defineEmits<{ close: []; pick: [params: Record<string, number>] }>()
const { t } = useI18n()
const q = ref('')
const artists = ref<Artist[]>([])
const albums = ref<Album[]>([])
const genres = ref<Genre[]>([])
const decades = ref<number[]>([])
const loading = ref(true)
let timer: number | undefined

async function load() {
  const text = q.value.trim() || undefined
  loading.value = true
  try {
    if (props.kind === 'artist') artists.value = (await api<Page<Artist>>(`/artists${query({ q: text, limit: 60 })}`)).items
    if (props.kind === 'album') albums.value = (await api<Page<Album>>(`/albums${query({ q: text, limit: 60, sort: text ? 'title' : 'recent' })}`)).items
  } finally {
    loading.value = false
  }
}
onMounted(async () => {
  if (props.kind === 'genre') genres.value = (await api<{ items: Genre[] }>('/genres').catch(() => ({ items: [] }))).items
  else if (props.kind === 'decade') decades.value = (await api<{ decades: number[] }>('/stations').catch(() => ({ decades: [] }))).decades
  else await load()
  loading.value = false
})
watch(q, () => {
  if (props.kind !== 'artist' && props.kind !== 'album') return
  clearTimeout(timer)
  timer = window.setTimeout(load, 250)
})
onUnmounted(() => clearTimeout(timer))
const shownGenres = computed(() => {
  const text = q.value.trim().toLowerCase()
  return [...genres.value].sort((a, b) => b.track_count - a.track_count).filter((g) => !text || g.name.toLowerCase().includes(text))
})
const searchable = computed(() => props.kind !== 'decade')
</script>

<template>
  <BaseModal :title="t(`stations.pick_${kind}`)" @close="emit('close')">
    <div class="flex flex-col gap-3">
      <label v-if="searchable" class="flex h-11 items-center gap-2 rounded-full bg-surface px-4">
        <Search :size="18" :stroke-width="1.5" class="text-muted" aria-hidden="true" />
        <span class="sr-only">{{ t('search.label') }}</span>
        <input v-model="q" type="search" maxlength="200" :placeholder="t('search.label')" class="min-w-0 flex-1 bg-transparent text-[15px] outline-none" />
      </label>
      <p v-if="!loading && !(artists.length || albums.length || shownGenres.length || decades.length)" class="text-[14px] text-muted">{{ t('search.noResults') }}</p>
      <ul class="flex flex-col" :class="loading ? 'opacity-60' : ''">
        <template v-if="kind === 'artist'">
          <li v-for="a in artists" :key="a.id">
            <button type="button" class="flex w-full items-center gap-3 rounded-xl px-2 py-1.5 text-left hover:bg-surface" @click="emit('pick', { artist_id: a.id })">
              <ArtistPhoto :artist-id="a.id" :name="a.name" :version="a.image_v" class="size-11 flex-none" />
              <span class="flex min-w-0 flex-1 flex-col"><span class="truncate text-[15px]">{{ a.name }}</span><span class="text-[13px] text-muted">{{ t('common.tracks', a.track_count) }}</span></span>
              <ChevronRight :size="18" class="flex-none text-subtle" />
            </button>
          </li>
        </template>
        <template v-else-if="kind === 'album'">
          <li v-for="a in albums" :key="a.id">
            <button type="button" class="flex w-full items-center gap-3 rounded-xl px-2 py-1.5 text-left hover:bg-surface" @click="emit('pick', { album_id: a.id })">
              <CoverArt :album-id="a.id" :has-cover="a.has_cover" :version="a.cover_v" rounded="rounded-md" class="size-11 flex-none" />
              <span class="flex min-w-0 flex-1 flex-col"><span class="truncate text-[15px]">{{ a.title }}</span><span class="truncate text-[13px] text-muted">{{ a.artist || t('common.unknownArtist') }}<template v-if="a.year"> · {{ a.year }}</template></span></span>
              <ChevronRight :size="18" class="flex-none text-subtle" />
            </button>
          </li>
        </template>
        <template v-else-if="kind === 'genre'">
          <li v-for="g in shownGenres" :key="g.id">
            <button type="button" class="flex w-full items-center gap-3 rounded-xl px-3 py-3 text-left hover:bg-surface" @click="emit('pick', { genre_id: g.id })">
              <span class="min-w-0 flex-1 truncate text-[16px]">{{ g.name }}</span><span class="text-[13px] text-muted">{{ t('common.tracks', g.track_count) }}</span>
            </button>
          </li>
        </template>
        <template v-else>
          <li v-for="d in decades" :key="d">
            <button type="button" class="flex w-full items-center rounded-xl px-3 py-3 text-left text-[16px] hover:bg-surface" @click="emit('pick', { decade: d })">{{ t('stations.decadeName', { n: d }) }}</button>
          </li>
        </template>
      </ul>
    </div>
  </BaseModal>
</template>
