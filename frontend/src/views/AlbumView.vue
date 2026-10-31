<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ChevronRight, Heart, MonitorPlay } from '@lucide/vue'
import { api } from '../api'
import { duration } from '../format'
import { errorMessage } from '../i18n'
import { usePlayer } from '../stores/player'
import { useUi } from '../stores/ui'
import type { AlbumDetail } from '../types'
import AccountMenu from '../components/AccountMenu.vue'
import CoverArt from '../components/CoverArt.vue'
import PlayerIcons from '../components/PlayerIcons.vue'
import QualityBadge from '../components/QualityBadge.vue'
import StarRating from '../components/StarRating.vue'
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
// the album's own like and stars (each person's), saved right away
async function like() {
  const a = album.value!
  a.is_favorite = !a.is_favorite
  try {
    await api(`/favorites/albums/${a.id}`, { method: a.is_favorite ? 'PUT' : 'DELETE' })
  } catch (e) {
    a.is_favorite = !a.is_favorite
    ui.notify(errorMessage(e), true)
  }
}

async function rate(stars: number | null) {
  const a = album.value!
  const before = a.rating
  a.rating = stars
  try {
    await api(`/ratings/albums/${a.id}`, stars ? { method: 'PUT', body: { rating: stars } } : { method: 'DELETE' })
  } catch (e) {
    a.rating = before
    ui.notify(errorMessage(e), true)
  }
}

function videos() {
  const a = album.value!
  ui.videoTarget = { albumId: a.id, title: a.title, artist: a.artist }
}

const totalTime = computed(() => album.value?.tracks.reduce((s, x) => s + (x.duration ?? 0), 0) ?? 0)
const multiDisc = computed(() => new Set(album.value?.tracks.map((x) => x.disc_no ?? 1)).size > 1)
</script>

<template>
  <p v-if="error" class="font-light text-muted">{{ error }}</p>
  <div v-else-if="album" class="flex flex-col gap-7">
    <div class="flex justify-end md:hidden"><AccountMenu /></div>
    <div class="flex flex-col gap-6 sm:flex-row sm:items-end sm:gap-8">
      <CoverArt :album-id="album.id" :has-cover="album.has_cover" :version="album.cover_v" size="large" rounded="rounded-xl" class="w-full shadow-[0_16px_40px_rgba(17,17,19,0.18)] sm:w-60" />
      <div class="flex min-w-0 flex-col gap-2.5">
        <span class="flex flex-wrap items-center gap-2"><span class="text-sm font-light text-muted"><template v-if="album.kind === 'unofficial' || album.kind === 'compilation' || album.kind === 'soundtrack'">{{ t(`albums.kind_${album.kind}`) }} · </template><template v-if="album.year">{{ album.year }} · </template>{{ t('common.tracks', album.tracks.length) }} · <span class="font-display">{{ duration(totalTime) }}</span></span><QualityBadge :quality="album.quality" /></span>
        <h1 class="text-[30px] font-extrabold leading-tight tracking-tight md:text-[40px]">{{ album.title || t('common.unknownAlbum') }}</h1>
        <RouterLink v-if="album.artist_id" :to="{ name: 'artist', params: { id: album.artist_id } }" class="flex items-center text-lg font-medium">{{ album.artist }}<ChevronRight :size="18" :stroke-width="1.6" /></RouterLink>
        <span v-else class="text-lg text-muted">{{ t('common.unknownArtist') }}</span>
        <div class="flex flex-wrap items-center gap-x-2">
          <StarRating :value="album.rating" @rate="rate" />
          <span v-if="!album.rating && album.track_rating_avg" class="text-[13px] text-muted">{{ t('albums.trackAvg', { n: album.track_rating_avg }) }}</span>
        </div>
        <div class="mt-2 flex flex-wrap gap-2">
          <button type="button" class="flex h-11 items-center gap-2 rounded-full bg-ink px-[22px] text-[15px] text-on-ink" @click="player.playTracks(album.tracks, 0, { shuffle: false })">
            <PlayerIcons name="play" :size="16" :stroke="1.8" />{{ t('common.listenAll') }}
          </button>
          <button type="button" class="h-11 rounded-full border border-line-strong px-5 text-[15px]" @click="player.playTracks(album.tracks, 0, { shuffle: true })">{{ t('common.shuffleAll') }}</button>
          <button type="button" class="h-11 rounded-full border border-line-strong px-5 text-[15px]" @click="ui.playlistPicker = album.tracks">{{ t('common.addShort') }}</button>
          <button
            type="button"
            class="grid size-11 place-items-center rounded-full border border-line-strong"
            :class="album.is_favorite ? 'text-accent' : ''"
            :aria-label="album.is_favorite ? t('common.favoriteRemove') : t('common.favoriteAdd')"
            :aria-pressed="album.is_favorite"
            @click="like"
          >
            <Heart :size="19" :stroke-width="1.4" :fill="album.is_favorite ? 'currentColor' : 'none'" />
          </button>
          <button type="button" class="flex h-11 items-center gap-1.5 rounded-full border border-line-strong px-4 text-[15px]" @click="videos">
            <MonitorPlay :size="17" :stroke-width="1.4" />{{ t('common.videos') }}<template v-if="album.video_count"> {{ album.video_count }}</template>
          </button>
        </div>
      </div>
    </div>
    <TrackList :tracks="album.tracks" :show-cover="false" :show-album="false" :numbered="!multiDisc" />
  </div>
</template>
