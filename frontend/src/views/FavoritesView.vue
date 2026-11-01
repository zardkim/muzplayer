<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api'
import type { Album, Track } from '../types'
import AlbumGrid from '../components/AlbumGrid.vue'
import PageHeader from '../components/PageHeader.vue'
import PlayActions from '../components/PlayActions.vue'
import TrackList from '../components/TrackList.vue'

const { t } = useI18n()
const items = ref<Track[]>([])
const albums = ref<Album[]>([])
const loaded = ref(false)
const tab = ref<'songs' | 'albums'>('songs')
onMounted(async () => {
  const [songs, liked] = await Promise.all([
    api<{ items: Track[] }>('/favorites'),
    api<{ items: Album[] }>('/favorites/albums').catch(() => ({ items: [] })),
  ])
  items.value = songs.items
  albums.value = liked.items
  loaded.value = true
})
</script>

<template>
  <div class="flex flex-col gap-5">
    <PageHeader :title="t('favorites.title')" />
    <div class="flex gap-2" role="tablist">
      <button
        v-for="k in (['songs', 'albums'] as const)"
        :key="k"
        type="button"
        role="tab"
        :aria-selected="tab === k"
        class="h-[38px] rounded-full px-4 text-[15px]"
        :class="tab === k ? 'bg-ink text-on-ink' : 'bg-surface'"
        @click="tab = k"
      >
        {{ t(`favorites.${k}`) }} {{ k === 'songs' ? items.length : albums.length }}
      </button>
    </div>
    <template v-if="tab === 'albums'">
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
