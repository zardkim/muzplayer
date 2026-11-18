<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Ellipsis, FastForward, Heart, Infinity as Endless, List, MessageSquareQuote, MonitorPlay, Pause, Play, Repeat, Repeat1, Rewind, Shuffle, Volume, Volume2 } from '@lucide/vue'
import { coverShades } from '../coverColor'
import { codec, duration } from '../format'
import { errorMessage } from '../i18n'
import { isIos } from '../pwa'
import { useLibrary } from '../stores/library'
import { useLyrics } from '../stores/lyrics'
import { usePlayer } from '../stores/player'
import { useUi } from '../stores/ui'
import { SETTLE, usePullToClose, useSwipe } from '../swipe'
import CoverArt from './CoverArt.vue'
import LikeButton from './LikeButton.vue'
import LyricsPanel from './LyricsPanel.vue'
import PlayerMenu from './PlayerMenu.vue'
import QueueList from './QueueList.vue'
import SeekBar from './SeekBar.vue'
import SpeedButton from './SpeedButton.vue'
import Marquee from './Marquee.vue'

// The phone's full player, on the cover's own colours (top to bottom, changing smoothly with each
// song). Three faces: the cover, the lyrics, the queue (the buttons at the bottom switch between
// them); the song's actions are behind its •••. White on the colours in every theme (style.css .np).
const { t } = useI18n()
const player = usePlayer()
const library = useLibrary()
const ui = useUi()
const lyrics = useLyrics()
const preview = ref<number | null>(null)
const menu = ref(false)

// what fills the middle: the cover, the lyrics (ui.lyricsOpen, shared with the PC player), the queue
const queueOpen = ref(false)
const face = computed(() => (ui.lyricsOpen ? 'lyrics' : queueOpen.value ? 'queue' : 'cover'))
function show(f: 'cover' | 'lyrics' | 'queue') {
  ui.lyricsOpen = f === 'lyrics'
  queueOpen.value = f === 'queue'
  menu.value = false
}

// the background: the cover's top and bottom colours (style.css fades from one song's to the next)
const shades = ref<{ top: string; bottom: string } | null>(null)
watch(
  () => [player.current?.album_id, player.current?.cover_v, player.current?.has_cover] as const,
  async ([albumId, v, hasCover]) => {
    const found = albumId && hasCover ? await coverShades(albumId, v) : null
    if (player.current?.album_id === albumId) shades.value = found
  },
  { immediate: true },
)
const background = computed(() => (shades.value ? { '--np-top': shades.value.top, '--np-bottom': shades.value.bottom } : {}))

const lyricLine = computed(() => lyrics.line)
const remaining = computed(() => Math.max(0, player.duration - (preview.value ?? player.currentTime)))
// iPhone pages can't set the volume (only the side buttons can): no slider there
const volumeShown = !isIos

// gestures (phones): pull the player down to tuck it away (not from inside the lyrics or the queue,
// which scroll); swipe the cover for the next or previous song
const coverX = ref(0)
let fromList = false
const { dragY, settling, settle, pull } = usePullToClose(() => (ui.playerOpen = false), () => !fromList)
function pullStart(e: TouchEvent) {
  fromList = !!(e.target as Element | null)?.closest('[data-no-pull]')
  pull.onTouchstart(e)
}
// a tap on the cover shows the lyrics; two quick taps like the song (a heart pops up)
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
  tapTimer = window.setTimeout(() => show('lyrics'), 300)
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

function videos() {
  const tr = player.current
  if (tr) ui.videoTarget = { trackId: tr.id, title: tr.title, artist: tr.artist }
}
const repeatLabel = computed(() =>
  player.repeat === 'one' ? t('player.repeatOne') : player.repeat === 'all' ? t('player.repeatAll') : t('player.repeatOff'),
)
</script>

<template>
  <div
    v-if="player.current"
    role="dialog"
    aria-modal="true"
    :aria-label="t('player.nowPlaying')"
    class="np fixed inset-0 z-50 overflow-hidden"
    :class="settling ? SETTLE : ''"
    :style="[background, dragY ? { transform: `translate3d(0,${dragY}px,0)` } : {}]"
    @touchstart="pullStart"
    @touchmove="pull.onTouchmove"
    @touchend="pull.onTouchend"
    @touchcancel="pull.onTouchcancel"
  >
    <div class="relative mx-auto flex h-full max-w-md flex-col px-6 pb-[calc(env(safe-area-inset-bottom)+12px)] pt-[calc(env(safe-area-inset-top)+6px)]">
      <!-- the handle: pull it down (or tap it) to close -->
      <button type="button" class="mx-auto mb-3 grid h-6 w-20 flex-none place-items-center" :aria-label="t('player.close')" @click="ui.playerOpen = false">
        <span class="h-[5px] w-10 rounded-full bg-white/35" />
      </button>

      <!-- lyrics and queue: the song stays at the top (its cover takes you back to the big one) -->
      <div v-if="face !== 'cover'" class="flex flex-none items-center gap-3.5">
        <button type="button" class="flex-none" :aria-label="t('player.hideLyrics')" @click="show('cover')">
          <CoverArt :album-id="player.current.album_id" :has-cover="player.current.has_cover" :version="player.current.cover_v" rounded="rounded-lg" class="size-16 shadow-lg" />
        </button>
        <span class="flex min-w-0 flex-1 flex-col">
          <Marquee :text="player.current.title" class="text-[17px] font-semibold" />
          <span class="truncate text-[16px] text-soft">{{ player.current.artist || t('common.unknownArtist') }}</span>
        </span>
        <LikeButton :track="player.current" :size="24" box="size-10" class="hover:bg-white/10" />
        <div class="relative">
          <button type="button" class="grid size-10 place-items-center rounded-full bg-white/10" :aria-label="t('common.moreActions')" :aria-expanded="menu" @click="menu = !menu">
            <Ellipsis :size="22" :stroke-width="2" />
          </button>
          <PlayerMenu v-if="menu" @close="menu = false" />
        </div>
      </div>

      <!-- the middle: the cover, the lyrics or the queue -->
      <div class="relative min-h-0 flex-1">
        <div
          v-if="face === 'cover'"
          class="flex h-full items-center justify-center [container-type:size]"
          @touchstart="flick.onTouchstart"
          @touchmove="flick.onTouchmove"
          @touchend="flick.onTouchend"
          @touchcancel="flick.onTouchcancel"
        >
          <button
            type="button"
            class="aspect-square w-[min(100cqw,100cqh)]"
            :class="settling ? SETTLE : ''"
            :style="coverX ? { transform: `translateX(${coverX}px)` } : undefined"
            :aria-label="t('player.showLyrics')"
            @click="coverTap"
          >
            <!-- smaller while paused, full size while it plays -->
            <span class="block h-full w-full transition-transform duration-500 ease-[cubic-bezier(0.2,0.9,0.3,1)]" :class="player.playing ? 'scale-100' : 'scale-[0.86]'">
              <CoverArt :album-id="player.current.album_id" :has-cover="player.current.has_cover" :version="player.current.cover_v" size="large" rounded="rounded-xl" class="h-full w-full shadow-[0_18px_50px_rgba(0,0,0,0.45)]" />
            </span>
          </button>
          <span v-if="burst" :key="burst" class="heart-burst pointer-events-none absolute inset-0 grid place-items-center text-like" aria-hidden="true">
            <Heart :size="96" fill="currentColor" :stroke-width="0" />
          </span>
        </div>

        <LyricsPanel v-else-if="face === 'lyrics'" bold data-no-pull class="h-full pt-2" />

        <div v-else class="flex h-full flex-col pt-5">
          <!-- how the queue plays: shuffled, repeated, and on with similar songs when it ends -->
          <div class="grid flex-none grid-cols-3 gap-2.5">
            <button
              type="button"
              class="grid h-11 place-items-center rounded-full transition-colors"
              :class="player.shuffle ? 'bg-white/85 text-[#111]' : 'bg-white/15'"
              :aria-label="player.shuffle ? t('player.shuffleOn') : t('player.shuffleOff')"
              :aria-pressed="player.shuffle"
              @click="player.toggleShuffle()"
            >
              <Shuffle :size="21" :stroke-width="2" />
            </button>
            <button
              type="button"
              class="grid h-11 place-items-center rounded-full transition-colors"
              :class="player.repeat !== 'off' ? 'bg-white/85 text-[#111]' : 'bg-white/15'"
              :aria-label="repeatLabel"
              @click="player.cycleRepeat()"
            >
              <Repeat1 v-if="player.repeat === 'one'" :size="21" :stroke-width="2" />
              <Repeat v-else :size="21" :stroke-width="2" />
            </button>
            <button
              type="button"
              class="grid h-11 place-items-center rounded-full transition-colors"
              :class="ui.playerPrefs.autoplay ? 'bg-white/85 text-[#111]' : 'bg-white/15'"
              :aria-label="t('settings.autoplayOn')"
              :title="t('settings.autoplayOn')"
              :aria-pressed="ui.playerPrefs.autoplay"
              @click="ui.playerPrefs.autoplay = !ui.playerPrefs.autoplay"
            >
              <Endless :size="23" :stroke-width="2" />
            </button>
          </div>
          <h3 class="mt-5 flex-none text-[19px] font-bold">{{ t('player.upNext') }}</h3>
          <QueueList data-no-pull class="-mx-4 mt-1 min-h-0 flex-1 overflow-y-auto pb-2" />
        </div>
      </div>

      <!-- the cover: the song under it -->
      <div v-if="face === 'cover'" class="mt-6 flex flex-none items-center gap-2">
        <span class="flex min-w-0 flex-1 flex-col">
          <Marquee :text="player.current.title" class="text-[22px] font-semibold leading-tight" />
          <span class="truncate text-[19px] text-soft">{{ player.current.artist || t('common.unknownArtist') }}<template v-if="ui.playerPrefs.showYear && player.current.year"> · {{ player.current.year }}</template></span>
          <!-- the line being sung, when the song has synced lyrics (a tap opens them) -->
          <button v-if="lyrics.lyrics?.synced" type="button" class="h-5 truncate text-left text-[14px] text-white/80" :aria-label="t('player.showLyrics')" @click="show('lyrics')">{{ lyricLine }}</button>
        </span>
        <LikeButton :track="player.current" :size="26" box="size-11" class="hover:bg-white/10" />
        <div class="relative">
          <button type="button" class="grid size-10 place-items-center rounded-full bg-white/10" :aria-label="t('common.moreActions')" :aria-expanded="menu" @click="menu = !menu">
            <Ellipsis :size="22" :stroke-width="2" />
          </button>
          <PlayerMenu v-if="menu" up @close="menu = false" />
        </div>
      </div>

      <!-- where it is: elapsed, the file's format (and speed), what is left -->
      <div class="mt-5 flex-none">
        <SeekBar :value="player.currentTime" :max="player.duration" :label="t('player.seek')" @change="player.seek" @preview="(v) => (preview = v)" />
        <div class="-mt-0.5 flex items-center justify-between font-display text-[13px] tabular-nums text-soft">
          <span class="w-14">{{ duration(preview ?? player.currentTime) }}</span>
          <span class="flex items-center gap-1.5">
            <span class="rounded-md bg-white/10 px-2 py-0.5 text-[11px] uppercase tracking-wide">{{ ui.playerPrefs.showCodec ? codec(player.current) : player.current.format }}</span>
            <SpeedButton v-if="ui.playerPrefs.musicSpeed" />
          </span>
          <span class="w-14 text-right">-{{ duration(remaining) }}</span>
        </div>
      </div>

      <div class="mt-3 flex flex-none items-center justify-around">
        <button type="button" class="grid size-16 place-items-center rounded-full active:bg-white/10" :aria-label="t('player.prev')" @click="player.prev()">
          <Rewind :size="40" fill="currentColor" :stroke-width="1" />
        </button>
        <button type="button" class="grid size-20 place-items-center rounded-full transition-transform active:scale-90" :aria-label="player.playing ? t('player.pause') : t('player.play')" @click="player.toggle()">
          <Pause v-if="player.playing" :size="50" fill="currentColor" :stroke-width="0" />
          <Play v-else :size="50" fill="currentColor" :stroke-width="1" class="translate-x-0.5" />
        </button>
        <button type="button" class="grid size-16 place-items-center rounded-full active:bg-white/10" :aria-label="t('player.next')" @click="player.next()">
          <FastForward :size="40" fill="currentColor" :stroke-width="1" />
        </button>
      </div>

      <div v-if="volumeShown" class="mt-3 flex flex-none items-center gap-3 text-soft">
        <Volume :size="18" fill="currentColor" :stroke-width="1.5" class="flex-none" />
        <SeekBar :value="player.volume" :max="1" :label="t('player.volume')" @change="(v) => (player.volume = v)" @preview="(v) => v !== null && (player.volume = v)" />
        <Volume2 :size="20" :stroke-width="1.5" class="flex-none" />
      </div>

      <!-- lyrics · (videos) · queue: the open one sits in a circle -->
      <div class="mt-3 grid flex-none grid-cols-3 items-center">
        <button
          type="button"
          class="grid size-12 place-items-center justify-self-start rounded-full transition-colors"
          :class="face === 'lyrics' ? 'bg-white/25' : ''"
          :aria-label="face === 'lyrics' ? t('player.hideLyrics') : t('player.showLyrics')"
          :aria-pressed="face === 'lyrics'"
          @click="show(face === 'lyrics' ? 'cover' : 'lyrics')"
        >
          <MessageSquareQuote :size="24" :stroke-width="1.8" />
        </button>
        <button v-if="player.current.has_video" type="button" class="grid size-12 place-items-center justify-self-center rounded-full" :aria-label="t('common.watchVideos')" @click="videos">
          <MonitorPlay :size="24" :stroke-width="1.8" />
        </button>
        <span v-else />
        <button
          type="button"
          class="relative grid size-12 place-items-center justify-self-end rounded-full transition-colors"
          :class="face === 'queue' ? 'bg-white/25' : ''"
          :aria-label="t('player.queue')"
          :aria-pressed="face === 'queue'"
          @click="show(face === 'queue' ? 'cover' : 'queue')"
        >
          <List :size="25" :stroke-width="2" />
          <!-- shuffled: a small mark on it -->
          <span v-if="player.shuffle && face !== 'queue'" class="absolute -right-0.5 -top-0.5 grid size-5 place-items-center rounded-full bg-white/25" aria-hidden="true"><Shuffle :size="11" :stroke-width="2.4" /></span>
        </button>
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
