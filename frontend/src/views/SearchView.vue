<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Search } from '@lucide/vue'
import { api, query } from '../api'
import type { Album, Artist, Page, Track } from '../types'
import AlbumGrid from '../components/AlbumGrid.vue'
import TrackList from '../components/TrackList.vue'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const q = typeof route.query.q === 'string' ? route.query.q.trim() : ''
const text = ref(q)
const tracks = ref<Track[]>([])
const albums = ref<Album[]>([])
const artists = ref<Artist[]>([])
const loaded = ref(false)

onMounted(async () => {
  if (!q) return
  const [tr, al, ar] = await Promise.all([
    api<Page<Track>>(`/tracks${query({ q, limit: 50 })}`),
    api<Page<Album>>(`/albums${query({ q, limit: 12, sort: 'title' })}`),
    api<Page<Artist>>(`/artists${query({ q, limit: 12 })}`),
  ])
  tracks.value = tr.items
  albums.value = al.items
  artists.value = ar.items
  loaded.value = true
})

function submit() {
  if (text.value.trim()) router.push({ name: 'search', query: { q: text.value.trim() } })
}
</script>

<template>
  <div class="flex flex-col gap-8">
    <form role="search" class="flex h-11 items-center gap-2.5 rounded-xl border border-line bg-surface px-3.5 md:hidden" @submit.prevent="submit">
      <Search :size="18" class="text-muted" aria-hidden="true" />
      <label for="m-search" class="sr-only">{{ t('search.label') }}</label>
      <input id="m-search" v-model="text" type="search" :placeholder="t('search.placeholder')" class="min-w-0 flex-1 bg-transparent text-base outline-none placeholder:text-subtle" />
    </form>

    <p v-if="!q" class="text-muted">{{ t('search.hint') }}</p>
    <template v-else>
      <h1 class="text-[28px] font-bold">{{ t('search.resultsFor', { q }) }}</h1>
      <p v-if="loaded && !tracks.length && !albums.length && !artists.length" class="text-muted">{{ t('search.noResults') }}</p>
      <section v-if="artists.length" class="flex flex-col gap-3">
        <h2 class="text-xl font-bold">{{ t('artists.title') }}</h2>
        <div class="flex flex-wrap gap-2">
          <RouterLink v-for="a in artists" :key="a.id" :to="{ name: 'artist', params: { id: a.id } }" class="rounded-full bg-surface-2 px-4 py-2 text-sm hover:bg-line">{{ a.name }}</RouterLink>
        </div>
      </section>
      <section v-if="albums.length" class="flex flex-col gap-3">
        <h2 class="text-xl font-bold">{{ t('albums.title') }}</h2>
        <AlbumGrid :albums="albums" row />
      </section>
      <section v-if="tracks.length" class="flex flex-col gap-2">
        <h2 class="text-xl font-bold">{{ t('tracks.title') }}</h2>
        <TrackList :tracks="tracks" />
      </section>
    </template>
  </div>
</template>
