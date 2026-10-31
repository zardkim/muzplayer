<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { Camera } from '@lucide/vue'
import { api } from '../api'
import { errorMessage } from '../i18n'
import { useAuth } from '../stores/auth'
import { usePlayer } from '../stores/player'
import type { ArtistDetail } from '../types'
import AlbumGrid from '../components/AlbumGrid.vue'
import ArtistPhoto from '../components/ArtistPhoto.vue'
import ArtistPhotoSheet from '../components/ArtistPhotoSheet.vue'
import PlayerIcons from '../components/PlayerIcons.vue'
import TrackList from '../components/TrackList.vue'

const props = defineProps<{ id: string }>()
const { t } = useI18n()
const player = usePlayer()
const auth = useAuth()
const photoSheet = ref(false)
const artist = ref<ArtistDetail | null>(null)
const error = ref('')

const official = computed(() => artist.value?.albums.filter((a) => a.kind !== 'unofficial') ?? [])
const unofficial = computed(() => artist.value?.albums.filter((a) => a.kind === 'unofficial') ?? [])

async function load() {
  try {
    artist.value = await api<ArtistDetail>(`/artists/${props.id}`)
  } catch (e) {
    error.value = errorMessage(e)
  }
}
onMounted(load)

function photoChanged() {
  photoSheet.value = false
  load()
}
</script>

<template>
  <p v-if="error" class="font-light text-muted">{{ error }}</p>
  <div v-else-if="artist" class="flex flex-col gap-8">
    <header class="flex flex-col items-center gap-5 text-center md:flex-row md:items-end md:gap-8 md:text-left">
      <div class="relative w-44 flex-none md:w-56">
        <ArtistPhoto :artist-id="artist.id" :name="artist.name" :version="artist.image_v" size="large" class="shadow-[0_16px_40px_rgba(17,17,19,0.18)]" />
        <button
          v-if="auth.user?.is_admin"
          type="button"
          class="absolute bottom-1 right-1 grid size-10 place-items-center rounded-full bg-bg/90 shadow hover:bg-bg"
          :aria-label="t('artists.photoTitle')"
          :title="t('artists.photoTitle')"
          @click="photoSheet = true"
        >
          <Camera :size="18" :stroke-width="1.6" />
        </button>
      </div>
      <div class="flex min-w-0 flex-col gap-3 md:pb-2">
        <span class="text-[13px] font-medium uppercase tracking-[0.14em] text-muted">{{ t('artists.label') }}</span>
        <h1 class="text-[32px] font-bold leading-tight md:text-[44px]">{{ artist.name }}</h1>
        <span class="text-[15px] font-light text-muted">
          <template v-if="artist.albums.length">{{ t('common.albums', artist.albums.length) }} · </template>{{ t('common.tracks', artist.tracks.length) }}
        </span>
        <div v-if="artist.tracks.length" class="flex flex-wrap justify-center gap-2 md:justify-start">
          <button type="button" class="flex h-11 items-center gap-2 rounded-full bg-ink px-[22px] text-[15px] text-on-ink" @click="player.playTracks(artist.tracks, 0, { shuffle: false })">
            <PlayerIcons name="play" :size="16" :stroke="1.8" />{{ t('common.listenAll') }}
          </button>
          <button type="button" class="h-11 rounded-full border border-line-strong px-5 text-[15px]" @click="player.playTracks(artist.tracks, 0, { shuffle: true })">{{ t('common.shuffleAll') }}</button>
        </div>
        <a v-if="artist.image_credit" :href="artist.image_credit.url" target="_blank" rel="noopener noreferrer" class="text-[12px] font-light text-subtle hover:text-muted hover:underline">
          {{ t('artists.photoCredit', { title: artist.image_credit.title }) }}
        </a>
      </div>
    </header>
    <ArtistPhotoSheet v-if="photoSheet" :artist="artist" @close="photoSheet = false" @changed="photoChanged" />
    <section v-if="official.length" class="flex flex-col gap-4">
      <h2 class="text-[22px] font-bold">{{ t('artists.albums') }}</h2>
      <AlbumGrid :albums="official" />
    </section>
    <section v-if="unofficial.length" class="flex flex-col gap-4">
      <h2 class="text-[22px] font-bold">{{ t('artists.unofficial') }}</h2>
      <AlbumGrid :albums="unofficial" />
    </section>
    <section v-if="artist.tracks.length" class="flex flex-col gap-1">
      <h2 class="text-[22px] font-bold">{{ t('artists.tracks') }}</h2>
      <TrackList :tracks="artist.tracks" />
    </section>
  </div>
</template>
