<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { ChevronDown, ChevronUp, EllipsisVertical, Heart, ListPlus, MonitorPlay } from '@lucide/vue'
import { coverGlow } from '../coverColor'
import { codec, duration } from '../format'
import { errorMessage } from '../i18n'
import { useLibrary } from '../stores/library'
import { useLyrics } from '../stores/lyrics'
import { usePlayer } from '../stores/player'
import { useUi } from '../stores/ui'
import { useSwipe } from '../swipe'
import CoverArt from './CoverArt.vue'
import LikeButton from './LikeButton.vue'
import LyricsPanel from './LyricsPanel.vue'
import PlayerControls from './PlayerControls.vue'
import QueueIcon from './QueueIcon.vue'
import SeekBar from './SeekBar.vue'
import SpeedButton from './SpeedButton.vue'
import StarRating from './StarRating.vue'

const { t } = useI18n()
const player = usePlayer()
const library = useLibrary()
const ui = useUi()
const lyrics = useLyrics()
const preview = ref<number | null>(null)
const menu = ref(false)
const glow = ref('var(--player-glow)')

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

// soft background tint from the album art's average colour
watch(
  () => [player.current?.album_id, player.current?.cover_v] as const,
  async ([albumId, v]) => {
    glow.value = 'var(--player-glow)'
    if (albumId && player.current?.has_cover) glow.value = (await coverGlow(albumId, v)) ?? glow.value
  },
  { immediate: true },
)

const lyricLine = computed(() => lyrics.line)

// gestures (phones): pull the player down to tuck it away; swipe the artwork for the next or previous song
const sheet = ref<HTMLElement | null>(null)
const dragY = ref(0)
const coverX = ref(0)
const settling = ref(false) // animating back or away after a release
function settle(apply: () => void, after?: () => void) {
  settling.value = true
  apply()
  window.setTimeout(() => {
    settling.value = false
    after?.()
  }, 220)
}
const pull = useSwipe({
  axes: ['y'],
  allow: (_, __, dy) => dy > 0 && (sheet.value?.scrollTop ?? 0) <= 0,
  move: (_, __, dy) => (dragY.value = Math.max(0, dy)),
  end: ({ dy, fast }) => {
    if (dy > 140 || (fast && dy > 40)) settle(() => (dragY.value = window.innerHeight), () => {
      ui.playerOpen = false
      dragY.value = 0
    })
    else settle(() => (dragY.value = 0))
  },
})
// a tap on the artwork shows the lyrics; two quick taps like the song (a heart pops up)
let lastTap = 0
let tapTimer = 0
const burst = ref(0)
function coverTap() {
  const now = Date.now()
  if (now - lastTap < 300) {
    window.clearTimeout(tapTimer)
    lastTap = 0
    burst.value++
    if (player.current && !library.isFavorite(player.current)) library.toggleFavorite(player.current).catch((e) => ui.notify(errorMessage(e), true))
    return
  }
  lastTap = now
  tapTimer = window.setTimeout(() => (ui.lyricsOpen = true), 300)
}

const flick = useSwipe({
  axes: ['x'],
  move: (_, dx) => (coverX.value = dx),
  end: ({ dx, fast }) => {
    if (Math.abs(dx) < 90 && !(fast && Math.abs(dx) > 30)) return settle(() => (coverX.value = 0))
    const next = dx < 0
    settle(() => (coverX.value = (next ? -1 : 1) * window.innerWidth), () => {
      if (next) player.next()
      else player.prev()
      coverX.value = 0
    })
  },
})
</script>

<template>
  <div
    v-if="player.current"
    role="dialog"
    aria-modal="true"
    :aria-label="t('player.nowPlaying')"
    ref="sheet"
    class="fixed inset-0 z-50 overflow-y-auto bg-sheet text-ink"
    :class="dragY ? 'overflow-hidden' : ''"
    @touchstart="pull.onTouchstart"
    @touchmove="pull.onTouchmove"
    @touchend="pull.onTouchend"
    @touchcancel="pull.onTouchcancel"
  >
    <div
      class="relative mx-auto flex min-h-full max-w-md flex-col md:my-6 md:min-h-0 md:overflow-hidden md:rounded-3xl md:shadow-2xl"
      :class="settling ? 'transition-transform duration-200 ease-out' : ''"
      :style="dragY ? { transform: `translateY(${dragY}px)` } : undefined"
    >
      <div
        class="pointer-events-none absolute inset-x-[-80px] bottom-[-80px] top-[40%] opacity-50"
        :style="{ background: `radial-gradient(60% 45% at 15% 20%, ${glow} 0%, transparent 70%), radial-gradient(55% 40% at 95% 15%, ${glow} 0%, transparent 70%)` }"
      />

      <div class="relative overflow-hidden" @touchstart="flick.onTouchstart" @touchmove="flick.onTouchmove" @touchend="flick.onTouchend" @touchcancel="flick.onTouchcancel">
        <!-- full width, but capped on short screens so the controls stay visible; tap toggles lyrics -->
        <!-- the artwork's height; clear of the top buttons and of the seek bar below -->
        <div v-if="ui.lyricsOpen" class="mx-auto h-[min(100vw,28rem,50dvh)] w-full pb-5 pt-[calc(env(safe-area-inset-top)+10px)]">
          <LyricsPanel />
        </div>
        <button
          v-else
          type="button"
          class="block w-full"
          :class="settling ? 'transition-transform duration-200 ease-out' : ''"
          :style="coverX ? { transform: `translateX(${coverX}px)` } : undefined"
          :aria-label="t('player.showLyrics')"
          @click="coverTap"
        >
          <CoverArt :album-id="player.current.album_id" :has-cover="player.current.has_cover" :version="player.current.cover_v" size="large" rounded="rounded-none" class="mx-auto w-full max-w-[min(100%,50dvh)]" />
        </button>
        <span v-if="burst" :key="burst" class="heart-burst pointer-events-none absolute inset-0 grid place-items-center text-like" aria-hidden="true">
          <Heart :size="96" fill="currentColor" :stroke-width="0" />
        </span>
        <button
          type="button"
          class="absolute right-3 grid size-11 place-items-center rounded-full bg-bg/70 backdrop-blur"
          style="top: calc(env(safe-area-inset-top) + 10px)"
          :aria-label="t('player.close')"
          @click="ui.playerOpen = false"
        >
          <ChevronDown :size="24" :stroke-width="1.4" />
        </button>
      </div>

      <div class="relative -mt-3">
        <SeekBar :value="player.currentTime" :max="player.duration" :label="t('player.seek')" track="color-mix(in srgb, var(--color-ink) 12%, transparent)" @change="player.seek" @preview="(v) => (preview = v)" />
      </div>

      <div class="relative flex flex-1 flex-col px-5 pb-[calc(1.5rem+env(safe-area-inset-bottom))]">
        <div class="flex items-center justify-between font-display text-sm text-soft">
          <span>{{ duration(preview ?? player.currentTime) }}</span>
          <span class="flex items-center gap-2">
            <span class="text-[12px] uppercase tracking-wide">{{ ui.playerPrefs.showCodec ? codec(player.current) : player.current.format }}</span>
            <SpeedButton v-if="ui.playerPrefs.musicSpeed" />
          </span>
          <span>{{ duration(player.duration) }}</span>
        </div>

        <div class="mt-1 flex items-center justify-between">
          <span class="flex">
            <button type="button" class="grid size-11 place-items-center" :aria-label="t('common.addToPlaylist')" @click="ui.playlistPicker = [player.current]">
              <ListPlus :size="24" :stroke-width="1.3" />
            </button>
            <button v-if="player.current.has_video" type="button" class="grid size-11 place-items-center" :aria-label="t('common.watchVideos')" @click="videos">
              <MonitorPlay :size="23" :stroke-width="1.3" />
            </button>
          </span>
          <LikeButton :track="player.current" :size="26" />
          <div class="relative">
            <button type="button" class="grid size-11 place-items-center" :aria-label="t('common.moreActions')" @click="menu = !menu">
              <EllipsisVertical :size="22" :stroke-width="1.3" />
            </button>
            <div v-if="menu" class="absolute bottom-12 right-0 z-10 flex w-52 flex-col overflow-hidden rounded-2xl border border-line bg-bg py-1.5 text-[15px] shadow-xl">
              <RouterLink v-if="player.current.album_id && player.current.album_kind !== 'chart'" :to="{ name: 'album', params: { id: player.current.album_id } }" class="px-4 py-3 hover:bg-surface" @click="menu = false">{{ t('common.goToAlbum') }}</RouterLink>
              <RouterLink v-if="player.current.artist_id" :to="{ name: 'artist', params: { id: player.current.artist_id } }" class="px-4 py-3 hover:bg-surface" @click="menu = false">{{ t('common.goToArtist') }}</RouterLink>
              <button type="button" class="px-4 py-3 text-left hover:bg-surface" @click="videos">{{ t('common.watchVideos') }}</button>
            </div>
          </div>
        </div>

        <!-- with the lyrics up the artwork is gone from the top: a small one beside the title, the two centred -->
        <div v-if="ui.lyricsOpen" class="mt-2 flex items-center justify-center gap-3.5">
          <button type="button" class="flex-none" :aria-label="t('player.hideLyrics')" @click="ui.lyricsOpen = false">
            <CoverArt :album-id="player.current.album_id" :has-cover="player.current.has_cover" :version="player.current.cover_v" rounded="rounded-lg" class="size-[72px] shadow-md" />
          </button>
          <span class="flex min-w-0 max-w-[70%] flex-col items-start gap-0.5">
            <span class="line-clamp-2 text-xl font-medium leading-snug">{{ player.current.title }}</span>
            <span class="truncate text-[16px] font-light text-soft">{{ player.current.artist || t('common.unknownArtist') }}<template v-if="ui.playerPrefs.showYear && player.current.year"> · {{ player.current.year }}</template></span>
            <StarRating :value="library.rating(player.current)" :size="16" @rate="rate" />
          </span>
        </div>
        <div v-else class="mt-2 flex flex-col items-center gap-1 text-center">
          <span class="line-clamp-2 text-2xl font-medium">{{ player.current.title }}</span>
          <span class="text-[17px] font-light text-soft">{{ player.current.artist || t('common.unknownArtist') }}<template v-if="ui.playerPrefs.showYear && player.current.year"> · {{ player.current.year }}</template></span>
          <StarRating :value="library.rating(player.current)" :size="18" @rate="rate" />
          <!-- fixed-height slot so the controls don't jump when a line appears -->
          <span class="h-[22px] max-w-full">
            <button
              v-if="lyricLine && !ui.lyricsOpen"
              type="button"
              class="line-clamp-1 text-[15px] text-accent"
              :aria-label="t('player.showLyrics')"
              @click="ui.lyricsOpen = true"
            >{{ lyricLine }}</button>
          </span>
        </div>

        <div class="mt-3"><PlayerControls large /></div>

        <div class="mt-auto flex items-center justify-between pt-2">
          <button
            type="button"
            class="h-9 rounded-full border px-3.5 text-[14px]"
            :class="ui.lyricsOpen ? 'border-ink bg-ink text-on-ink' : 'border-line-strong'"
            :aria-pressed="ui.lyricsOpen"
            @click="ui.lyricsOpen = !ui.lyricsOpen"
          >
            {{ t('player.lyrics') }}
          </button>
          <button type="button" class="flex h-11 items-center gap-1.5 px-3 text-[15px]" @click="ui.queueOpen = true">
            {{ t('player.upNextButton') }} <ChevronUp :size="16" :stroke-width="1.6" />
          </button>
          <span class="flex items-center">
            <button type="button" class="grid size-11 place-items-center" :aria-label="t('player.queue')" @click="ui.queueOpen = true">
              <QueueIcon />
            </button>
          </span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* the double-tap heart: pops up, then fades */
.heart-burst {
  animation: heart-burst 0.8s ease-out forwards;
}
@keyframes heart-burst {
  0% { opacity: 0; transform: scale(0.4); }
  20% { opacity: 0.95; transform: scale(1.1); }
  40% { transform: scale(1); }
  100% { opacity: 0; transform: scale(1.05); }
}
</style>
