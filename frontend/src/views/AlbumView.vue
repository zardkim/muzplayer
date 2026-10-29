<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ListPlus, Play, Shuffle } from '@lucide/vue'
import { api } from '../api'
import { duration } from '../format'
import { errorMessage } from '../i18n'
import { usePlayer } from '../stores/player'
import { useUi } from '../stores/ui'
import type { AlbumDetail } from '../types'
import CoverArt from '../components/CoverArt.vue'
import TrackList from '../components/TrackList.vue'

const props = defineProps<{ id: string }>()
const { t } = useI18n()
const player = usePlayer()
const ui = useUi()
const album = ref<AlbumDetail | null>(null)
const error = ref('')

onMounted(async () => {
  try {
    album.value = await api<AlbumDetail>(`/albums/${props.id}`)
  } catch (e) {
    error.value = errorMessage(e)
  }
})
const totalTime = computed(() => album.value?.tracks.reduce((s, x) => s + (x.duration ?? 0), 0) ?? 0)
const multiDisc = computed(() => new Set(album.value?.tracks.map((x) => x.disc_no ?? 1)).size > 1)
</script>

<template>
  <p v-if="error" class="text-muted">{{ error }}</p>
  <div v-else-if="album" class="flex flex-col gap-8">
    <div class="flex flex-col gap-6 sm:flex-row sm:items-end">
      <CoverArt :album-id="album.id" :has-cover="album.has_cover" size="large" class="w-full max-w-[260px] shadow-2xl shadow-black/40 sm:w-56" />
      <div class="flex min-w-0 flex-col gap-3">
        <h1 class="text-3xl font-bold tracking-tight md:text-4xl">{{ album.title || t('common.unknownAlbum') }}</h1>
        <p class="text-muted">
          <RouterLink v-if="album.artist_id" :to="{ name: 'artist', params: { id: album.artist_id } }" class="font-semibold text-ink hover:text-accent-strong">{{ album.artist }}</RouterLink>
          <span v-else>{{ t('common.unknownArtist') }}</span>
          <template v-if="album.year"> · {{ album.year }}</template>
          · {{ t('common.tracks', album.tracks.length) }} · <span class="font-display">{{ duration(totalTime) }}</span>
        </p>
        <div class="mt-1 flex flex-wrap gap-2">
          <button type="button" class="flex h-11 items-center gap-2 rounded-full bg-accent px-5 font-semibold text-bg" @click="player.playTracks(album.tracks, 0, { shuffle: false })">
            <Play :size="18" fill="currentColor" />{{ t('common.playAll') }}
          </button>
          <button type="button" class="flex h-11 items-center gap-2 rounded-full border border-line-strong px-5 font-semibold" @click="player.playTracks(album.tracks, 0, { shuffle: true })">
            <Shuffle :size="18" />{{ t('common.shuffleAll') }}
          </button>
          <button type="button" class="grid size-11 place-items-center rounded-full bg-surface-2" :aria-label="t('common.addToPlaylist')" @click="ui.playlistPicker = album.tracks">
            <ListPlus :size="18" />
          </button>
        </div>
      </div>
    </div>
    <TrackList :tracks="album.tracks" :show-cover="false" :show-album="false" :numbered="!multiDisc" />
  </div>
</template>
