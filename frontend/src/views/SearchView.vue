<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ChevronRight, Search } from '@lucide/vue'
import { api, query } from '../api'
import type { Album, Artist, Chart, Genre, Page, Track } from '../types'
import AlbumGrid from '../components/AlbumGrid.vue'
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
const loaded = ref(false)

// stable colour per artist tile, dark enough for white text
const TILE = ['#A34A6E', '#3F6FB5', '#5B4BD6', '#8A6516', '#2F7D6D', '#B0482D', '#6B5B95', '#3D5A80']
const tileColor = (name: string) => TILE[[...name].reduce((s, c) => s + c.charCodeAt(0), 0) % TILE.length]

onMounted(async () => {
  if (q) {
    const [tr, al, ar] = await Promise.all([
      api<Page<Track>>(`/tracks${query({ q, limit: 50 })}`),
      api<Page<Album>>(`/albums${query({ q, limit: 12, sort: 'title' })}`),
      api<Page<Artist>>(`/artists${query({ q, limit: 12 })}`),
    ])
    tracks.value = tr.items
    albums.value = al.items
    artists.value = ar.items
  } else {
    const [g, ar, ch] = await Promise.all([
      api<{ items: Genre[] }>('/genres').catch(() => ({ items: [] })),
      api<Page<Artist>>('/artists?limit=500').catch(() => ({ items: [], total: 0 })),
      api<Page<Chart>>('/charts?limit=12').catch(() => ({ items: [], total: 0 })),
    ])
    charts.value = ch.items
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
      <p v-if="loaded && !tracks.length && !albums.length && !artists.length" class="font-light text-muted">{{ t('search.noResults') }}</p>
      <section v-if="artists.length" class="flex flex-wrap gap-2.5">
        <RouterLink v-for="a in artists" :key="a.id" :to="{ name: 'artist', params: { id: a.id } }" class="flex h-11 items-center rounded-full border border-line-strong px-[18px] font-light">{{ a.name }}</RouterLink>
      </section>
      <section v-if="albums.length" class="flex flex-col gap-3">
        <h3 class="text-lg font-bold">{{ t('albums.title') }}</h3>
        <AlbumGrid :albums="albums" row />
      </section>
      <section v-if="tracks.length" class="flex flex-col gap-1">
        <h3 class="text-lg font-bold">{{ t('tracks.title') }}</h3>
        <TrackList :tracks="tracks" />
      </section>
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
