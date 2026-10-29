<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api'
import { errorMessage } from '../i18n'
import { usePlayer } from '../stores/player'
import type { ArtistDetail } from '../types'
import AlbumGrid from '../components/AlbumGrid.vue'
import PageHeader from '../components/PageHeader.vue'
import PlayerIcons from '../components/PlayerIcons.vue'
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
  <p v-if="error" class="font-light text-muted">{{ error }}</p>
  <div v-else-if="artist" class="flex flex-col gap-8">
    <PageHeader :title="artist.name" />
    <div v-if="artist.tracks.length" class="-mt-4 flex flex-wrap gap-2">
      <button type="button" class="flex h-11 items-center gap-2 rounded-full bg-ink px-[22px] text-[15px] text-white" @click="player.playTracks(artist.tracks, 0, { shuffle: false })">
        <PlayerIcons name="play" :size="16" :stroke="1.8" />{{ t('common.listenAll') }}
      </button>
      <button type="button" class="h-11 rounded-full border border-line-strong px-5 text-[15px]" @click="player.playTracks(artist.tracks, 0, { shuffle: true })">{{ t('common.shuffleAll') }}</button>
    </div>
    <section v-if="artist.albums.length" class="flex flex-col gap-4">
      <h2 class="text-[22px] font-bold">{{ t('artists.albums') }}</h2>
      <AlbumGrid :albums="artist.albums" />
    </section>
    <section v-if="artist.tracks.length" class="flex flex-col gap-1">
      <h2 class="text-[22px] font-bold">{{ t('artists.tracks') }}</h2>
      <TrackList :tracks="artist.tracks" />
    </section>
  </div>
</template>
