<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Play, Shuffle } from '@lucide/vue'
import { api } from '../api'
import { useUi } from '../stores/ui'
import type { Album, Track, VideoListItem } from '../types'
import VideoCard from '../components/VideoCard.vue'
import AlbumGrid from '../components/AlbumGrid.vue'
import PageHeader from '../components/PageHeader.vue'
import PlayActions from '../components/PlayActions.vue'
import TrackList from '../components/TrackList.vue'

// Liked songs, albums and music videos (?tab=videos opens on the videos: My Music links there).
const { t } = useI18n()
const route = useRoute()
const ui = useUi()
const items = ref<Track[]>([])
const albums = ref<Album[]>([])
const videos = ref<VideoListItem[]>([])
const loaded = ref(false)
const TABS = ['songs', 'albums', 'videos'] as const
const tab = ref<(typeof TABS)[number]>((TABS as readonly string[]).includes(String(route.query.tab)) ? (route.query.tab as (typeof TABS)[number]) : 'songs')
const counts = computed(() => ({ songs: items.value.length, albums: albums.value.length, videos: videos.value.length }))
onMounted(async () => {
  const [songs, liked, vids] = await Promise.all([
    api<{ items: Track[] }>('/favorites'),
    api<{ items: Album[] }>('/favorites/albums').catch(() => ({ items: [] })),
    api<{ items: VideoListItem[] }>('/videos?liked=true&limit=200').catch(() => ({ items: [] })),
  ])
  items.value = songs.items
  albums.value = liked.items
  videos.value = vids.items
  loaded.value = true
})

function playVideos(start: number, shuffle = false) {
  if (videos.value.length) ui.videoQueue = { items: videos.value, start, shuffle, title: t('favorites.videos') }
}
// unliked here: it leaves the list
function liked(v: VideoListItem, on: boolean) {
  if (!on) videos.value = videos.value.filter((x) => x.id !== v.id)
}
</script>

<template>
  <div class="flex flex-col gap-5">
    <PageHeader :title="t('favorites.title')" />
    <div class="flex gap-2" role="tablist">
      <button
        v-for="k in TABS"
        :key="k"
        type="button"
        role="tab"
        :aria-selected="tab === k"
        class="h-[38px] rounded-full px-4 text-[15px]"
        :class="tab === k ? 'bg-ink text-on-ink' : 'bg-surface'"
        @click="tab = k"
      >
        {{ t(`favorites.${k}`) }} {{ counts[k] }}
      </button>
    </div>
    <template v-if="tab === 'videos'">
      <div v-if="videos.length" class="flex gap-2">
        <button type="button" class="flex h-10 items-center gap-1.5 rounded-full bg-ink px-4 text-[14px] text-on-ink" @click="playVideos(0)">
          <Play :size="15" fill="currentColor" />{{ t('videos.playAll') }}
        </button>
        <button type="button" class="flex h-10 items-center gap-1.5 rounded-full border border-line-strong px-4 text-[14px]" @click="playVideos(Math.floor(Math.random() * videos.length), true)">
          <Shuffle :size="16" :stroke-width="1.6" />{{ t('videos.shufflePlay') }}
        </button>
      </div>
      <p v-if="loaded && !videos.length" class="font-light text-muted">{{ t('favorites.videosEmpty') }}</p>
      <ul class="grid grid-cols-1 gap-x-4 gap-y-6 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        <li v-for="(v, i) in videos" :key="v.id"><VideoCard :video="v" @play="playVideos(i)" @liked="(on) => liked(v, on)" /></li>
      </ul>
    </template>
    <template v-else-if="tab === 'albums'">
      <p v-if="loaded && !albums.length" class="font-light text-muted">{{ t('favorites.albumsEmpty') }}</p>
      <AlbumGrid :albums="albums" />
    </template>
    <template v-else>
    <div v-if="items.length" class="flex gap-2">
      <PlayActions :tracks="items" />
    </div>
    <p v-if="loaded && !items.length" class="font-light text-muted">{{ t('favorites.empty') }}</p>
    <TrackList :tracks="items" />
    </template>
  </div>
</template>
