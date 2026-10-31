<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ChevronRight, Search } from '@lucide/vue'
import { api, query } from '../api'
import { appConfig } from '../config'
import type { Album, Artist, Book, Chart, CollectionsHome, Genre, Page, Track } from '../types'
import AlbumGrid from '../components/AlbumGrid.vue'
import ArtistPhoto from '../components/ArtistPhoto.vue'
import BookGrid from '../components/BookGrid.vue'
import ChartGrid from '../components/ChartGrid.vue'
import PageHeader from '../components/PageHeader.vue'
import TrackList from '../components/TrackList.vue'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const q = typeof route.query.q === 'string' ? route.query.q.trim() : ''
const text = ref(q)
const tracks = ref<Track[]>([])
const albums = ref<Album[]>([])
const artists = ref<Artist[]>([])
const genres = ref<Genre[]>([])
const charts = ref<Chart[]>([])
const books = ref<Book[]>([])
const loaded = ref(false)

// stable colour per artist tile, dark enough for white text
const TILE = ['#A34A6E', '#3F6FB5', '#5B4BD6', '#8A6516', '#2F7D6D', '#B0482D', '#6B5B95', '#3D5A80']
const tileColor = (name: string) => TILE[[...name].reduce((s, c) => s + c.charCodeAt(0), 0) % TILE.length]

// search results, one tab per kind ("all" shows the first few of each)
type Kind = 'tracks' | 'albums' | 'artists' | 'books'
const PAGE: Record<Kind, number> = { tracks: 50, albums: 36, artists: 48, books: 36 }
const total = reactive<Record<Kind, number>>({ tracks: 0, albums: 0, artists: 0, books: 0 })
const busy = ref(false)
// (kept on the page, not in the URL: the page is kept alive per URL, so a tab change would reload it)
const tab = ref<Kind | 'all'>('all')
const tabs = computed(() =>
  (['tracks', 'albums', 'artists', 'books'] as Kind[]).filter((k) => total[k] > 0).map((k) => ({ key: k, label: t(`search.tab_${k}`), n: total[k] })),
)
function pick(key: Kind | 'all') {
  tab.value = key
}

async function fetchKind(kind: Kind, offset: number) {
  const n = PAGE[kind]
  if (kind === 'tracks') return api<Page<Track>>(`/tracks${query({ q, limit: n, offset, sort: 'relevance' })}`)
  if (kind === 'albums') return api<Page<Album>>(`/albums${query({ q, limit: n, offset, sort: 'title' })}`)
  if (kind === 'artists') return api<Page<Artist>>(`/artists${query({ q, limit: n, offset })}`)
  return api<Page<Book>>(`/books${query({ q, limit: n, offset })}`)
}
const lists = { tracks, albums, artists, books } as const
async function more(kind: Kind) {
  busy.value = true
  try {
    const r = await fetchKind(kind, lists[kind].value.length)
    ;(lists[kind].value as unknown[]).push(...r.items)
  } finally {
    busy.value = false
  }
}

onMounted(async () => {
  if (q) {
    const kinds: Kind[] = appConfig.audiobooks ? ['tracks', 'albums', 'artists', 'books'] : ['tracks', 'albums', 'artists']
    await Promise.all(
      kinds.map(async (k) => {
        const r = await fetchKind(k, 0).catch(() => ({ items: [], total: 0 }))
        ;(lists[k].value as unknown[]) = r.items
        total[k] = r.total ?? r.items.length
      }),
    )
  } else {
    const [g, ar, ch] = await Promise.all([
      api<{ items: Genre[] }>('/genres').catch(() => ({ items: [] })),
      api<Page<Artist>>('/artists?limit=500').catch(() => ({ items: [], total: 0 })),
      api<CollectionsHome>('/collections/home').catch(() => null),
    ])
    // the newest week of each chart source and today's themes
    const seen = new Set<number>()
    charts.value = ch ? [...ch.hero, ...ch.picks].filter((c) => !seen.has(c.id) && seen.add(c.id)).slice(0, 12) : []
    genres.value = [...g.items].sort((a, b) => b.track_count - a.track_count).slice(0, 16)
    artists.value = [...ar.items].sort((a, b) => b.track_count - a.track_count).slice(0, 8)
  }
  loaded.value = true
})

function submit() {
  if (text.value.trim()) router.push({ name: 'search', query: { q: text.value.trim() } })
}
</script>

<template>
  <div class="flex flex-col gap-7">
    <PageHeader :title="t('explore.title')" />
    <form role="search" class="flex h-[50px] items-center gap-2.5 rounded-full bg-surface px-[18px]" @submit.prevent="submit">
      <Search :size="22" :stroke-width="1.4" class="text-muted" aria-hidden="true" />
      <label for="explore-search" class="sr-only">{{ t('search.label') }}</label>
      <input id="explore-search" v-model="text" type="search" enterkeyhint="search" :placeholder="t('search.placeholder')" class="min-w-0 flex-1 bg-transparent text-[17px] font-light outline-none placeholder:text-muted" />
    </form>

    <template v-if="q">
      <h2 class="text-[22px] font-bold">{{ t('search.resultsFor', { q }) }}</h2>
      <p v-if="loaded && !tabs.length" class="font-light text-muted">{{ t('search.noResults') }}</p>
      <nav v-if="tabs.length" :aria-label="t('search.label')" class="-mx-5 -mt-3 flex gap-1.5 overflow-x-auto px-5 [scrollbar-width:none] md:mx-0 md:px-0">
        <button
          v-for="x in [{ key: 'all', label: t('search.tab_all'), n: 0 }, ...tabs]"
          :key="x.key"
          type="button"
          class="h-[38px] flex-none rounded-full border px-4 text-[15px]"
          :class="tab === x.key ? 'border-ink bg-ink text-on-ink' : 'border-line-strong bg-bg'"
          :aria-pressed="tab === x.key"
          @click="pick(x.key as Kind | 'all')"
        >
          {{ x.label }}<span v-if="x.n" class="ml-1 font-display text-[13px] opacity-70">{{ x.n > 999 ? '999+' : x.n }}</span>
        </button>
      </nav>

      <!-- all: the first few of each, each with a way into its tab -->
      <template v-if="tab === 'all'">
        <section v-if="artists.length" class="flex flex-col gap-3">
          <button type="button" class="flex items-center gap-1 self-start text-lg font-bold" @click="pick('artists')">{{ t('search.tab_artists') }} <ChevronRight :size="18" :stroke-width="1.6" /></button>
          <div class="flex flex-wrap gap-2.5">
            <RouterLink v-for="a in artists.slice(0, 8)" :key="a.id" :to="{ name: 'artist', params: { id: a.id } }" class="flex h-11 items-center gap-2.5 rounded-full border border-line-strong pl-1.5 pr-[18px] font-light">
              <ArtistPhoto :artist-id="a.id" :name="a.name" :version="a.image_v" class="size-8 flex-none" />{{ a.name }}
            </RouterLink>
          </div>
        </section>
        <section v-if="tracks.length" class="flex flex-col gap-1">
          <button type="button" class="flex items-center gap-1 self-start text-lg font-bold" @click="pick('tracks')">{{ t('search.tab_tracks') }} <ChevronRight :size="18" :stroke-width="1.6" /></button>
          <TrackList :tracks="tracks.slice(0, 5)" />
        </section>
        <section v-if="albums.length" class="flex flex-col gap-3">
          <button type="button" class="flex items-center gap-1 self-start text-lg font-bold" @click="pick('albums')">{{ t('search.tab_albums') }} <ChevronRight :size="18" :stroke-width="1.6" /></button>
          <AlbumGrid :albums="albums.slice(0, 12)" row />
        </section>
        <section v-if="books.length" class="flex flex-col gap-3">
          <button type="button" class="flex items-center gap-1 self-start text-lg font-bold" @click="pick('books')">{{ t('search.tab_books') }} <ChevronRight :size="18" :stroke-width="1.6" /></button>
          <BookGrid :books="books.slice(0, 12)" row />
        </section>
      </template>

      <TrackList v-else-if="tab === 'tracks'" :tracks="tracks" />
      <AlbumGrid v-else-if="tab === 'albums'" :albums="albums" />
      <ul v-else-if="tab === 'artists'" class="grid grid-cols-3 gap-x-4 gap-y-6 sm:grid-cols-[repeat(auto-fill,minmax(130px,1fr))]">
        <li v-for="a in artists" :key="a.id">
          <RouterLink :to="{ name: 'artist', params: { id: a.id } }" class="flex flex-col items-center gap-2.5 text-center">
            <ArtistPhoto :artist-id="a.id" :name="a.name" :version="a.image_v" size="thumb" class="w-full" />
            <span class="flex w-full min-w-0 flex-col">
              <span class="truncate text-[15px]">{{ a.name }}</span>
              <span class="truncate text-[13px] font-light text-muted">{{ t('common.tracks', a.track_count) }}</span>
            </span>
          </RouterLink>
        </li>
      </ul>
      <BookGrid v-else-if="tab === 'books'" :books="books" />
      <button
        v-if="tab !== 'all' && lists[tab].value.length < total[tab]"
        type="button"
        class="mx-auto h-11 rounded-full border border-line-strong px-6 text-[15px]"
        :disabled="busy"
        @click="more(tab)"
      >
        {{ busy ? t('common.loading') : t('common.loadMore') }}
      </button>
    </template>

    <template v-else>
      <section v-if="charts.length" class="flex flex-col gap-3.5">
        <RouterLink to="/charts" class="flex items-center gap-1 text-[22px] font-bold">{{ t('explore.charts') }} <ChevronRight :size="22" :stroke-width="1.6" /></RouterLink>
        <ChartGrid :charts="charts" row />
      </section>
      <section v-if="genres.length" class="flex flex-col gap-3.5">
        <RouterLink to="/genres" class="flex items-center gap-1 text-[22px] font-bold">{{ t('explore.genres') }} <ChevronRight :size="22" :stroke-width="1.6" /></RouterLink>
        <div class="flex flex-wrap gap-2.5">
          <RouterLink
            v-for="g in genres"
            :key="g.id"
            :to="{ name: 'tracks', query: { genre: g.id } }"
            class="flex h-11 items-center rounded-full border border-line-strong px-[18px] text-base font-light hover:border-ink"
          >#{{ g.name }}</RouterLink>
        </div>
      </section>
      <section v-if="artists.length" class="flex flex-col gap-3.5">
        <RouterLink to="/artists" class="flex items-center gap-1 text-[22px] font-bold">{{ t('explore.artists') }} <ChevronRight :size="22" :stroke-width="1.6" /></RouterLink>
        <div class="grid grid-cols-2 gap-2.5 md:grid-cols-4">
          <RouterLink
            v-for="a in artists"
            :key="a.id"
            :to="{ name: 'artist', params: { id: a.id } }"
            class="flex h-[76px] items-center rounded-md px-4 text-[17px] font-bold text-white"
            :style="{ background: tileColor(a.name) }"
          >
            <span class="line-clamp-2">{{ a.name }}</span>
          </RouterLink>
        </div>
      </section>
    </template>
  </div>
</template>
