<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Play, Shuffle } from '@lucide/vue'
import { api, query } from '../api'
import { usePlayer } from '../stores/player'
import type { Genre, Page, Track } from '../types'
import TrackList from '../components/TrackList.vue'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const player = usePlayer()
const sort = computed(() => (typeof route.query.sort === 'string' ? route.query.sort : 'title'))
const genreId = typeof route.query.genre === 'string' ? Number(route.query.genre) : undefined
const genreName = ref('')
const items = ref<Track[]>([])
const total = ref(0)
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    const page = await api<Page<Track>>(`/tracks${query({ sort: sort.value, genre_id: genreId, limit: 200, offset: items.value.length })}`)
    items.value.push(...page.items)
    total.value = page.total
  } finally {
    loading.value = false
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
  <div class="flex flex-col gap-6">
    <div class="flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 class="text-[32px] font-bold tracking-tight">{{ genreName || t('tracks.title') }}</h1>
        <p class="mt-1 text-sm text-muted">{{ t('common.tracks', total) }}</p>
      </div>
      <div class="flex flex-wrap gap-2">
        <button type="button" class="flex h-11 items-center gap-2 rounded-full bg-accent px-5 font-semibold text-bg" :disabled="!items.length" @click="player.playTracks(items, 0, { shuffle: false })">
          <Play :size="18" fill="currentColor" />{{ t('common.playAll') }}
        </button>
        <button type="button" class="flex h-11 items-center gap-2 rounded-full border border-line-strong px-5 font-semibold" :disabled="!items.length" @click="player.playTracks(items, 0, { shuffle: true })">
          <Shuffle :size="18" />{{ t('common.shuffleAll') }}
        </button>
      </div>
    </div>
    <div v-if="!genreId" class="flex gap-1.5">
      <button
        v-for="s in sorts"
        :key="s.key"
        type="button"
        class="h-9 rounded-full px-3.5 text-[13px]"
        :class="sort === s.key ? 'bg-ink font-semibold text-bg' : 'bg-surface-2 text-ink'"
        @click="router.replace({ query: { ...route.query, sort: s.key } })"
      >
        {{ t(s.label) }}
      </button>
    </div>
    <TrackList :tracks="items" />
    <button v-if="items.length < total" type="button" class="mx-auto h-11 rounded-full bg-surface-2 px-6 text-sm" :disabled="loading" @click="load">
      {{ loading ? t('common.loading') : t('common.loadMore') }}
    </button>
  </div>
</template>
