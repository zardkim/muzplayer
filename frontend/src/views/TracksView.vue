<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { api, query } from '../api'
import { usePlayer } from '../stores/player'
import type { Genre, Page, Track } from '../types'
import PageHeader from '../components/PageHeader.vue'
import PlayerIcons from '../components/PlayerIcons.vue'
import TrackList from '../components/TrackList.vue'
import TrackTiles from '../components/TrackTiles.vue'
import ViewToggle from '../components/ViewToggle.vue'
import { useUi } from '../stores/ui'
import type { ViewMode } from '../types'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const player = usePlayer()
const ui = useUi()
const view = computed(() => (ui.views.tracks as ViewMode) || 'list')
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
  <div class="flex flex-col gap-5">
    <PageHeader :title="genreName ? `#${genreName}` : t('tracks.title')" :sub="t('common.tracks', total)" />
    <div class="flex items-center gap-2">
    <div class="-mr-5 flex min-w-0 flex-1 gap-2 overflow-x-auto pr-5 [scrollbar-width:none] md:mr-0 md:pr-0">
      <button type="button" class="flex h-[38px] flex-none items-center gap-1.5 rounded-full bg-ink px-4 text-[15px] text-white" :disabled="!items.length" @click="player.playTracks(items, 0, { shuffle: false })">
        <PlayerIcons name="play" :size="14" :stroke="2" />{{ t('common.listenAll') }}
      </button>
      <button type="button" class="h-[38px] flex-none rounded-full border border-line-strong px-4 text-[15px]" :disabled="!items.length" @click="player.playTracks(items, 0, { shuffle: true })">{{ t('common.shuffleAll') }}</button>
      <template v-if="!genreId">
        <span class="mx-1 w-px flex-none bg-line" />
        <button
          v-for="s in sorts"
          :key="s.key"
          type="button"
          class="h-[38px] flex-none rounded-full border px-4 text-[15px]"
          :class="sort === s.key ? 'border-ink' : 'border-line-strong text-muted'"
          @click="router.replace({ query: { ...route.query, sort: s.key } })"
        >
          {{ t(s.label) }}
        </button>
      </template>
    </div>
    <ViewToggle page="tracks" fallback="list" />
    </div>
    <TrackList v-if="view === 'list'" :tracks="items" />
    <TrackTiles v-else :tracks="items" :dense="view === 'grid'" />
    <button v-if="items.length < total" type="button" class="mx-auto h-11 rounded-full border border-line-strong px-6 text-[15px]" :disabled="loading" @click="load">
      {{ loading ? t('common.loading') : t('common.loadMore') }}
    </button>
  </div>
</template>
