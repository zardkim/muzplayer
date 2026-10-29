<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { Play, Shuffle } from '@lucide/vue'
import { api } from '../api'
import { errorMessage } from '../i18n'
import { usePlayer } from '../stores/player'
import type { ArtistDetail } from '../types'
import AlbumGrid from '../components/AlbumGrid.vue'
import TrackList from '../components/TrackList.vue'

const props = defineProps<{ id: string }>()
const { t } = useI18n()
const player = usePlayer()
const artist = ref<ArtistDetail | null>(null)
const error = ref('')

onMounted(async () => {
  try {
    artist.value = await api<ArtistDetail>(`/artists/${props.id}`)
  } catch (e) {
    error.value = errorMessage(e)
  }
})
</script>

<template>
  <p v-if="error" class="text-muted">{{ error }}</p>
  <div v-else-if="artist" class="flex flex-col gap-9">
    <div class="flex flex-col gap-4">
      <h1 class="text-4xl font-bold tracking-tight">{{ artist.name }}</h1>
      <div v-if="artist.tracks.length" class="flex flex-wrap gap-2">
        <button type="button" class="flex h-11 items-center gap-2 rounded-full bg-accent px-5 font-semibold text-bg" @click="player.playTracks(artist.tracks, 0, { shuffle: false })">
          <Play :size="18" fill="currentColor" />{{ t('common.playAll') }}
        </button>
        <button type="button" class="flex h-11 items-center gap-2 rounded-full border border-line-strong px-5 font-semibold" @click="player.playTracks(artist.tracks, 0, { shuffle: true })">
          <Shuffle :size="18" />{{ t('common.shuffleAll') }}
        </button>
      </div>
    </div>
    <section v-if="artist.albums.length" class="flex flex-col gap-4">
      <h2 class="text-xl font-bold">{{ t('artists.albums') }}</h2>
      <AlbumGrid :albums="artist.albums" />
    </section>
    <section v-if="artist.tracks.length" class="flex flex-col gap-2">
      <h2 class="text-xl font-bold">{{ t('artists.tracks') }}</h2>
      <TrackList :tracks="artist.tracks" />
    </section>
  </div>
</template>
