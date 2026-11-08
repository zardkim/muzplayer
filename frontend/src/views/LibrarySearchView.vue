<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ChevronRight, Folder, Search } from '@lucide/vue'
import { api, query } from '../api'
import { listSearchFor } from '../listSearch'
import type { Album, Artist, Chart, Page, Track } from '../types'
import AlbumGrid from '../components/AlbumGrid.vue'
import ArtistPhoto from '../components/ArtistPhoto.vue'
import ChartGrid from '../components/ChartGrid.vue'
import CoverArt from '../components/CoverArt.vue'
import PageHeader from '../components/PageHeader.vue'
import SearchBox from '../components/SearchBox.vue'
import TrackList from '../components/TrackList.vue'

// The library searched as a whole (a phone's library page, its 🔍): what matches, kind by kind —
// albums, artists, songs (the lists' own search), and genres, folders, charts and themes that are
// named so or hold matching songs (api library/search). "All" opens the kind's tab searched for it.
type Found = {
  genres: { id: number; name: string; match_count: number; track_count: number }[]
  folders: { path: string; name: string; match_count: number; track_count: number; cover: { id: number; v: number } | null }[]
  charts: (Chart & { match_count: number })[]
}
const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const text = ref(typeof route.query.q === 'string' ? route.query.q : '')
const q = computed(() => (typeof route.query.q === 'string' ? route.query.q.trim() : ''))
const albums = ref<Page<Album> | null>(null)
const artists = ref<Page<Artist> | null>(null)
const tracks = ref<Page<Track> | null>(null)
const found = ref<Found | null>(null)
const loading = ref(false)
let asked = 0

async function load() {
  const term = q.value
  if (!term) return
  const mine = ++asked
  loading.value = true
  try {
    const [a, r, s, f] = await Promise.all([
      api<Page<Album>>(`/albums${query({ q: term, sort: 'title', limit: 12 })}`),
      api<Page<Artist>>(`/artists${query({ q: term, limit: 12 })}`),
      api<Page<Track>>(`/tracks${query({ q: term, sort: 'relevance', limit: 6 })}`),
      api<Found>(`/library/search${query({ q: term })}`),
    ])
    if (mine !== asked) return
    albums.value = a
    artists.value = r
    tracks.value = s
    found.value = f
  } finally {
    if (mine === asked) loading.value = false
  }
}
watch(q, load)
onMounted(() => {
  load()
  // opened from the 🔍: straight to typing
  if (!q.value) nextTick(() => (document.getElementById('lib-search-all') as HTMLInputElement | null)?.focus())
})

function submit(v: string) {
  const term = v.trim()
  ;(document.activeElement as HTMLElement | null)?.blur()
  if (term) router.replace({ query: { q: term } })
}
// a kind's tab, searched for it
function openTab(name: 'albums' | 'artists' | 'tracks') {
  listSearchFor(() => name).value = q.value
  router.push({ name })
}
const charts = computed(() => found.value?.charts.filter((c) => c.kind === 'chart') ?? [])
const themes = computed(() => found.value?.charts.filter((c) => c.kind === 'theme') ?? [])
const nothing = computed(
  () => !loading.value && !!found.value && !albums.value?.total && !artists.value?.total && !tracks.value?.total && !found.value.genres.length && !found.value.folders.length && !found.value.charts.length,
)
const heading = 'flex items-center gap-1 self-start text-lg font-bold'
</script>

<template>
  <div class="flex flex-col gap-7">
    <PageHeader :title="t('libSearch.title')" :icon="Search" />
    <SearchBox id="lib-search-all" v-model="text" large :placeholder="t('libSearch.placeholder')" @submit="submit" />
    <p v-if="!q" class="font-light text-muted">{{ t('libSearch.hint') }}</p>
    <p v-else-if="nothing" class="font-light text-muted">{{ t('search.noResults') }}</p>

    <template v-if="q && found">
      <section v-if="albums?.total" class="flex flex-col gap-3">
        <button type="button" :class="heading" @click="openTab('albums')">{{ t('nav.albums') }} <span class="text-[14px] font-normal text-muted">{{ albums.total }}</span><ChevronRight :size="18" :stroke-width="1.6" /></button>
        <AlbumGrid :albums="albums.items" row />
      </section>
      <section v-if="artists?.total" class="flex flex-col gap-3">
        <button type="button" :class="heading" @click="openTab('artists')">{{ t('nav.artists') }} <span class="text-[14px] font-normal text-muted">{{ artists.total }}</span><ChevronRight :size="18" :stroke-width="1.6" /></button>
        <div class="flex flex-wrap gap-2.5">
          <RouterLink v-for="a in artists.items" :key="a.id" :to="{ name: 'artist', params: { id: a.id } }" class="flex h-11 items-center gap-2.5 rounded-full border border-line-strong pl-1.5 pr-[18px] font-light">
            <ArtistPhoto :artist-id="a.id" :name="a.name" :version="a.image_v" class="size-8 flex-none" />{{ a.name }}
          </RouterLink>
        </div>
      </section>
      <section v-if="tracks?.total" class="flex flex-col gap-1">
        <button type="button" :class="heading" @click="openTab('tracks')">{{ t('nav.songs') }} <span class="text-[14px] font-normal text-muted">{{ tracks.total }}</span><ChevronRight :size="18" :stroke-width="1.6" /></button>
        <TrackList :tracks="tracks.items" />
      </section>
      <section v-if="found.genres.length" class="flex flex-col gap-3">
        <h2 :class="heading">{{ t('nav.genres') }}</h2>
        <div class="flex flex-wrap gap-2.5">
          <RouterLink
            v-for="g in found.genres"
            :key="g.id"
            :to="{ name: 'tracks', query: { genre: g.id } }"
            class="flex h-11 items-center gap-1.5 rounded-full border border-line-strong px-[18px] text-base font-light hover:border-ink"
          >#{{ g.name }}<span v-if="g.match_count" class="text-[13px] text-muted">{{ t('libSearch.matching', { n: g.match_count }) }}</span></RouterLink>
        </div>
      </section>
      <section v-if="found.folders.length" class="flex flex-col gap-1">
        <h2 :class="heading">{{ t('nav.folders') }}</h2>
        <ul class="flex flex-col">
          <li v-for="f in found.folders" :key="f.path">
            <RouterLink :to="{ name: 'folders', query: { path: f.path } }" class="flex items-center gap-3 rounded-xl py-2 hover:bg-surface">
              <CoverArt v-if="f.cover" :album-id="f.cover.id" :has-cover="true" :version="f.cover.v" rounded="rounded-lg" class="size-11 flex-none" />
              <span v-else class="grid size-11 flex-none place-items-center rounded-lg bg-surface text-muted"><Folder :size="20" :stroke-width="1.4" /></span>
              <span class="flex min-w-0 flex-col">
                <span class="truncate text-[15px]">{{ f.name }}</span>
                <span class="truncate text-[13px] font-light text-muted">{{ f.path }} · {{ t('libSearch.matching', { n: f.match_count }) }}</span>
              </span>
            </RouterLink>
          </li>
        </ul>
      </section>
      <section v-if="charts.length" class="flex flex-col gap-3">
        <h2 :class="heading">{{ t('charts.charts') }}</h2>
        <ChartGrid :charts="charts" row />
      </section>
      <section v-if="themes.length" class="flex flex-col gap-3">
        <h2 :class="heading">{{ t('charts.themes') }}</h2>
        <ChartGrid :charts="themes" row />
      </section>
    </template>
  </div>
</template>
