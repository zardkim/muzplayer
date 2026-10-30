<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { ChevronDown, Disc3, EllipsisVertical, ListPlus, MicVocal, MonitorPlay, Volume2, VolumeX } from '@lucide/vue'
import { coverGlow } from '../coverColor'
import { duration } from '../format'
import { errorMessage } from '../i18n'
import { useLibrary } from '../stores/library'
import { usePlayer } from '../stores/player'
import { useUi } from '../stores/ui'
import CoverArt from './CoverArt.vue'
import LikeButton from './LikeButton.vue'
import LyricsPanel from './LyricsPanel.vue'
import PlayerControls from './PlayerControls.vue'
import QueueList from './QueueList.vue'
import SeekBar from './SeekBar.vue'
import StarRating from './StarRating.vue'

// PC player: the artwork and controls on the left, lyrics or the queue on the right.
// (Phones keep NowPlaying.vue; App.vue picks one by the same breakpoint as the sidebar.)
const { t } = useI18n()
const player = usePlayer()
const library = useLibrary()
const ui = useUi()
const preview = ref<number | null>(null)
const menu = ref(false)
const glow = ref('#C9D6E3')

watch(
  () => [player.current?.album_id, player.current?.cover_v] as const,
  async ([albumId, v]) => {
    glow.value = '#C9D6E3'
    if (albumId && player.current?.has_cover) glow.value = (await coverGlow(albumId, v)) ?? glow.value
  },
  { immediate: true },
)

async function rate(stars: number | null) {
  if (!player.current) return
  try {
    await library.rate(player.current, stars)
  } catch (e) {
    ui.notify(errorMessage(e), true)
  }
}

function videos() {
  const tr = player.current
  if (!tr) return
  menu.value = false
  ui.videoTarget = { trackId: tr.id, title: tr.title, artist: tr.artist }
}

function close() {
  ui.playerOpen = false
}
const onKey = (e: KeyboardEvent) => e.key === 'Escape' && !ui.videoTarget && !ui.playlistPicker && close()
onMounted(() => window.addEventListener('keydown', onKey))
onUnmounted(() => window.removeEventListener('keydown', onKey))
</script>

<template>
  <div v-if="player.current" role="dialog" aria-modal="true" :aria-label="t('player.nowPlaying')" class="fixed inset-0 z-50 flex flex-col overflow-hidden bg-[#F7F6F2] text-ink">
    <div
      class="pointer-events-none absolute inset-0 opacity-60"
      :style="{ background: `radial-gradient(50% 60% at 18% 30%, ${glow} 0%, transparent 70%), radial-gradient(45% 55% at 90% 80%, ${glow} 0%, transparent 70%)` }"
    />

    <header class="relative flex h-16 flex-none items-center justify-between px-8">
      <button type="button" class="grid size-11 place-items-center rounded-full bg-white/70 backdrop-blur hover:bg-white" :aria-label="t('player.close')" @click="close">
        <ChevronDown :size="24" :stroke-width="1.4" />
      </button>
      <span class="text-[13px] font-medium uppercase tracking-[0.18em] text-muted">{{ t('player.nowPlaying') }}</span>
      <span class="size-11" />
    </header>

    <div class="relative grid min-h-0 flex-1 grid-cols-[minmax(0,1fr)_minmax(0,1fr)] gap-12 px-12 pb-10 xl:gap-20 xl:px-20">
      <!-- left: artwork, song, controls -->
      <section class="flex min-h-0 flex-col items-center justify-center gap-6">
        <CoverArt
          :album-id="player.current.album_id"
          :has-cover="player.current.has_cover"
          :version="player.current.cover_v"
          size="large"
          rounded="rounded-2xl"
          class="aspect-square w-full max-w-[min(100%,46vh)] shadow-[0_24px_60px_rgba(17,17,19,0.22)]"
        />

        <div class="flex w-full max-w-[min(100%,46vh)] flex-col gap-4">
          <div class="flex items-start gap-3">
            <div class="flex min-w-0 flex-1 flex-col">
              <span class="line-clamp-2 text-[26px] font-bold leading-tight">{{ player.current.title }}</span>
              <RouterLink
                v-if="player.current.artist_id"
                :to="{ name: 'artist', params: { id: player.current.artist_id } }"
                class="truncate text-[17px] text-[#52525B] hover:text-ink hover:underline"
                @click="close"
              >{{ player.current.artist }}</RouterLink>
              <span v-else class="truncate text-[17px] text-[#52525B]">{{ player.current.artist || t('common.unknownArtist') }}</span>
              <RouterLink
                v-if="player.current.album_id && player.current.album_kind !== 'chart' && player.current.album"
                :to="{ name: 'album', params: { id: player.current.album_id } }"
                class="truncate text-[14px] font-light text-muted hover:text-ink hover:underline"
                @click="close"
              >{{ player.current.album }}</RouterLink>
            </div>
            <LikeButton :track="player.current" :size="24" />
          </div>

          <div class="flex items-center justify-between">
            <StarRating :value="library.rating(player.current)" :size="20" @rate="rate" />
            <span class="flex items-center">
              <button type="button" class="grid size-10 place-items-center rounded-full hover:bg-white/70" :aria-label="t('common.addToPlaylist')" :title="t('common.addToPlaylist')" @click="ui.playlistPicker = [player.current]">
                <ListPlus :size="21" :stroke-width="1.3" />
              </button>
              <button type="button" class="grid size-10 place-items-center rounded-full hover:bg-white/70" :class="player.current.has_video ? '' : 'text-muted'" :aria-label="t('common.watchVideos')" :title="t('common.watchVideos')" @click="videos">
                <MonitorPlay :size="20" :stroke-width="1.3" />
              </button>
              <span class="relative">
                <button type="button" class="grid size-10 place-items-center rounded-full hover:bg-white/70" :aria-label="t('common.moreActions')" :aria-expanded="menu" @click="menu = !menu">
                  <EllipsisVertical :size="20" :stroke-width="1.3" />
                </button>
                <span v-if="menu" class="absolute bottom-11 right-0 z-10 flex w-52 flex-col overflow-hidden rounded-2xl border border-line bg-bg py-1.5 text-[15px] shadow-xl">
                  <RouterLink v-if="player.current.album_id && player.current.album_kind !== 'chart'" :to="{ name: 'album', params: { id: player.current.album_id } }" class="flex items-center gap-2.5 px-4 py-2.5 hover:bg-surface" @click="close"><Disc3 :size="18" :stroke-width="1.4" />{{ t('common.goToAlbum') }}</RouterLink>
                  <RouterLink v-if="player.current.artist_id" :to="{ name: 'artist', params: { id: player.current.artist_id } }" class="flex items-center gap-2.5 px-4 py-2.5 hover:bg-surface" @click="close"><MicVocal :size="18" :stroke-width="1.4" />{{ t('common.goToArtist') }}</RouterLink>
                </span>
              </span>
            </span>
          </div>

          <div class="flex flex-col gap-1">
            <SeekBar :value="player.currentTime" :max="player.duration" :label="t('player.seek')" track="rgb(17 17 19 / 0.12)" @change="player.seek" @preview="(v) => (preview = v)" />
            <div class="flex justify-between font-display text-[13px] text-[#52525B]">
              <span>{{ duration(preview ?? player.currentTime) }}</span>
              <span class="text-[11px] uppercase tracking-wide">{{ player.current.format }}</span>
              <span>{{ duration(player.duration) }}</span>
            </div>
          </div>

          <PlayerControls large />

          <div class="flex items-center gap-2.5 self-center">
            <button type="button" class="grid size-9 place-items-center rounded-full hover:bg-white/70" :aria-label="t('player.volume')" @click="player.volume = player.volume > 0 ? 0 : 1">
              <VolumeX v-if="player.volume === 0" :size="19" :stroke-width="1.3" />
              <Volume2 v-else :size="19" :stroke-width="1.3" />
            </button>
            <div class="w-40">
              <SeekBar :value="player.volume" :max="1" :label="t('player.volume')" fill="#111113" track="rgb(17 17 19 / 0.12)" @change="(v) => (player.volume = v)" @preview="(v) => v !== null && (player.volume = v)" />
            </div>
          </div>
        </div>
      </section>

      <!-- right: lyrics or the queue -->
      <section class="flex min-h-0 flex-col rounded-3xl bg-white/55 p-2 backdrop-blur-md">
        <div class="flex flex-none items-center gap-1 p-2" role="tablist">
          <button
            v-for="tab in (['lyrics', 'queue'] as const)"
            :key="tab"
            type="button"
            role="tab"
            class="h-10 rounded-full px-5 text-[15px] transition-colors"
            :class="ui.playerTab === tab ? 'bg-ink text-white' : 'hover:bg-white'"
            :aria-selected="ui.playerTab === tab"
            @click="ui.playerTab = tab"
          >
            {{ tab === 'lyrics' ? t('player.lyrics') : t('player.queue') }}
          </button>
          <button
            v-if="ui.playerTab === 'queue' && player.queue.length > player.index + 1"
            type="button"
            class="ml-auto h-9 rounded-full border border-line-strong px-3 text-[13px] hover:bg-white"
            @click="player.clearUpcoming()"
          >
            {{ t('player.clearQueue') }}
          </button>
        </div>
        <LyricsPanel v-if="ui.playerTab === 'lyrics'" large class="min-h-0 flex-1 px-6" />
        <QueueList v-else class="min-h-0 flex-1 overflow-y-auto px-2 pb-2" />
      </section>
    </div>
  </div>
</template>
