<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ChevronDown, MicVocal, Volume2, VolumeX } from '@lucide/vue'
import { duration } from '../format'
import { useLyrics } from '../stores/lyrics'
import { usePlayer } from '../stores/player'
import { openPlayer, togglePlayer } from '../playerNav'
import { useUi } from '../stores/ui'
import { useSwipe } from '../swipe'
import BookCover from './BookCover.vue'
import CoverArt from './CoverArt.vue'
import DevicesButton from './DevicesButton.vue'
import LikeButton from './LikeButton.vue'
import PlayerIcons from './PlayerIcons.vue'
import QueueIcon from './QueueIcon.vue'
import SeekBar from './SeekBar.vue'
import SkipIcon from './SkipIcon.vue'

// Desktop: floating pill at the bottom of the content column, with the line being sung;
// it can be tucked away (App.vue then shows a small button to bring it back).
// Phone: floating mini player above the tab bar (see App.vue for placement).
defineProps<{ mobile?: boolean }>()
const { t } = useI18n()
const player = usePlayer()
const lyrics = useLyrics()
const ui = useUi()

const preview = ref<number | null>(null)

const isBook = computed(() => player.mode === 'book' && !!player.book)

// phone mini player: swipe sideways for the next / previous song, up to open the player, down (or
// the ∨ at its end) to tuck it away (App.vue then shows a small button; it comes back by itself
// when something starts)
const slide = ref(0)
const sliding = ref(false)
const swipe = useSwipe({
  axes: ['x', 'y'],
  allow: (axis) => axis === 'x' ? !isBook.value && !!player.current : true,
  move: (axis, dx) => {
    if (axis === 'x') slide.value = dx * 0.6
  },
  end: ({ axis, dx, dy, fast }) => {
    if (axis === 'y') {
      if (dy < -30 && (player.current || isBook.value)) ui.playerOpen = true
      else if (dy > 30) ui.barHidden = true
      return
    }
    const go = Math.abs(dx) > 70 || (fast && Math.abs(dx) > 25)
    if (go) (dx < 0 ? player.next() : player.prev())
    sliding.value = true
    slide.value = 0
    window.setTimeout(() => (sliding.value = false), 200)
  },
})
const segLength = computed(() => Math.max(0, player.segment.end - player.segment.start))
const segPos = computed(() => Math.min(segLength.value, Math.max(0, player.bookPos - player.segment.start)))
</script>

<template>
  <!-- phone mini player -->
  <div
    v-if="mobile"
    class="glass relative flex h-[60px] items-center gap-3 overflow-hidden rounded-full pl-2 pr-1.5"
    @touchstart="swipe.onTouchstart"
    @touchmove="swipe.onTouchmove"
    @touchend="swipe.onTouchend"
    @touchcancel="swipe.onTouchcancel"
  >
    <template v-if="isBook && player.book">
      <button type="button" class="flex min-w-0 flex-1 items-center gap-3 text-left" :aria-label="t('player.open')" @click="ui.playerOpen = true">
        <BookCover :book-id="player.book.id" :has-cover="player.book.has_cover" :version="player.book.cover_v" square rounded="rounded-full" class="size-11 flex-none" />
        <span class="flex min-w-0 flex-col">
          <span class="truncate text-[15px]">{{ player.chapter?.title || player.book.title }}</span>
          <span class="truncate text-xs font-light text-muted">{{ player.chapter ? player.book.title : player.book.authors }}</span>
        </span>
      </button>
      <button type="button" class="grid size-11 place-items-center" :aria-label="player.playing ? t('player.pause') : t('player.play')" @click="player.toggle()">
        <PlayerIcons :name="player.playing ? 'pause' : 'play'" :size="24" :stroke="1.6" />
      </button>
      <button type="button" class="grid size-11 place-items-center" :aria-label="t('player.skipForward', { n: player.skipForward })" @click="player.skip(player.skipForward)">
        <SkipIcon :seconds="player.skipForward" forward :size="26" />
      </button>
      <button type="button" class="grid w-8 flex-none place-items-center self-stretch text-muted" :aria-label="t('player.hideBar')" @click="ui.barHidden = true"><ChevronDown :size="18" :stroke-width="1.6" /></button>
      <span class="absolute inset-x-6 bottom-0 h-[2px] bg-line">
        <span class="block h-full bg-accent" :style="{ width: player.book.duration ? `${(player.bookPos / player.book.duration) * 100}%` : '0%' }" />
      </span>
    </template>
    <template v-else-if="player.current">
      <button
        type="button"
        class="flex min-w-0 flex-1 items-center gap-3 text-left"
        :class="sliding ? 'transition-transform duration-200' : ''"
        :style="slide ? { transform: `translateX(${slide}px)` } : undefined"
        :aria-label="t('player.open')"
        @click="ui.playerOpen = true"
      >
        <CoverArt :album-id="player.current.album_id" :has-cover="player.current.has_cover" :version="player.current.cover_v" rounded="rounded-full" class="size-11 flex-none" />
        <span class="flex min-w-0 flex-col">
          <span class="truncate text-[15px]">{{ player.current.title }}</span>
          <span class="truncate text-xs font-light text-muted">{{ player.current.artist || t('common.unknownArtist') }}</span>
        </span>
      </button>
      <button type="button" class="grid size-11 place-items-center" :aria-label="player.playing ? t('player.pause') : t('player.play')" @click="player.toggle()">
        <PlayerIcons :name="player.playing ? 'pause' : 'play'" :size="24" :stroke="1.6" />
      </button>
      <button type="button" class="grid size-11 place-items-center" :aria-label="t('player.queue')" @click="ui.queueOpen = true">
        <QueueIcon />
      </button>
      <button type="button" class="grid w-8 flex-none place-items-center self-stretch text-muted" :aria-label="t('player.hideBar')" @click="ui.barHidden = true"><ChevronDown :size="18" :stroke-width="1.6" /></button>
      <span class="absolute inset-x-6 bottom-0 h-[2px] bg-line">
        <span class="block h-full bg-accent" :style="{ width: player.duration ? `${(player.currentTime / player.duration) * 100}%` : '0%' }" />
      </span>
    </template>
    <template v-else>
      <span class="min-w-0 flex-1 truncate pl-3 text-[15px] font-light text-muted">{{ t('player.notPlaying') }}</span>
      <button type="button" class="grid size-11 place-items-center text-muted" :aria-label="t('player.hideBar')" @click="ui.barHidden = true"><ChevronDown :size="20" :stroke-width="1.6" /></button>
      <span class="grid size-11 place-items-center text-subtle"><PlayerIcons name="play" /></span>
      <button type="button" class="grid size-11 place-items-center" :aria-label="t('player.queue')" @click="ui.queueOpen = true"><QueueIcon /></button>
    </template>
  </div>

  <!-- desktop floating player: audiobook -->
  <div v-else-if="isBook && player.book" :aria-label="t('player.nowPlaying')" class="glass flex h-[76px] items-center gap-4 rounded-full px-3.5">
    <button type="button" class="size-[52px] flex-none" :aria-label="t('player.open')" @click="ui.playerOpen = true">
      <BookCover :book-id="player.book.id" :has-cover="player.book.has_cover" :version="player.book.cover_v" square rounded="rounded-full" />
    </button>
    <RouterLink :to="{ name: 'book', params: { id: player.book.id } }" class="flex w-52 min-w-0 flex-col">
      <span class="truncate text-[15px]">{{ player.chapter?.title || player.book.title }}</span>
      <span class="truncate text-[13px] font-light text-muted">{{ player.chapter ? player.book.title : player.book.authors }}</span>
    </RouterLink>
    <div class="flex items-center">
      <button type="button" class="grid size-11 place-items-center" :aria-label="t('player.skipBack', { n: player.skipBack })" @click="player.skip(-player.skipBack)"><SkipIcon :seconds="player.skipBack" :size="28" /></button>
      <button type="button" class="grid size-12 place-items-center" :aria-label="player.playing ? t('player.pause') : t('player.play')" @click="player.toggle()">
        <PlayerIcons :name="player.playing ? 'pause' : 'play'" :size="28" :stroke="1.6" />
      </button>
      <button type="button" class="grid size-11 place-items-center" :aria-label="t('player.skipForward', { n: player.skipForward })" @click="player.skip(player.skipForward)"><SkipIcon :seconds="player.skipForward" forward :size="28" /></button>
    </div>
    <div class="flex min-w-0 flex-1 items-center gap-2.5 font-display text-xs text-muted">
      <span class="w-12 text-right">{{ duration(preview ?? segPos) }}</span>
      <SeekBar :value="segPos" :max="segLength" :label="t('player.seek')" @change="(v) => player.seekBook(player.segment.start + v)" @preview="(v) => (preview = v)" />
      <span class="w-12">-{{ duration(segLength - (preview ?? segPos)) }}</span>
    </div>
    <button type="button" class="h-9 rounded-full border border-line-strong px-3 font-display text-[13px]" :aria-label="t('player.speed')" @click="ui.playerOpen = true">{{ player.rate }}×</button>
    <button type="button" class="grid size-10 place-items-center" :aria-label="t('player.volume')" @click="player.volume = player.volume > 0 ? 0 : 1">
      <VolumeX v-if="player.volume === 0" :size="20" :stroke-width="1.3" />
      <Volume2 v-else :size="20" :stroke-width="1.3" />
    </button>
    <div class="w-20">
      <SeekBar :value="player.volume" :max="1" :label="t('player.volume')" fill="var(--color-ink)" @change="(v) => (player.volume = v)" @preview="(v) => v !== null && (player.volume = v)" />
    </div>
    <button type="button" class="grid size-9 place-items-center rounded-full text-muted hover:bg-surface hover:text-ink" :aria-label="t('player.hideBar')" :title="t('player.hideBar')" @click="ui.barHidden = true">
      <ChevronDown :size="18" :stroke-width="1.6" />
    </button>
  </div>

  <!-- desktop floating player -->
  <div v-else-if="player.current" :aria-label="t('player.nowPlaying')" class="glass relative flex h-[76px] items-center gap-3 rounded-full px-3.5 xl:gap-4">
    <button type="button" class="size-[52px] flex-none" :aria-label="t('player.open')" :aria-pressed="$route.name === 'playing'" @click="togglePlayer()">
      <CoverArt :album-id="player.current.album_id" :has-cover="player.current.has_cover" :version="player.current.cover_v" rounded="rounded-full" />
    </button>
    <div class="flex w-28 min-w-0 flex-col xl:w-52">
      <span class="truncate text-[15px]">{{ player.current.title }}</span>
      <RouterLink
        v-if="player.current.artist_id"
        :to="{ name: 'artist', params: { id: player.current.artist_id } }"
        class="truncate text-[13px] font-light text-muted hover:text-ink"
      >{{ player.current.artist }}</RouterLink>
      <span v-else class="truncate text-[13px] font-light text-muted">{{ player.current.artist || t('common.unknownArtist') }}</span>
    </div>
    <LikeButton :track="player.current" :size="20" box="size-10" />
    <div class="flex items-center">
      <button type="button" class="grid size-11 place-items-center" :aria-label="t('player.prev')" @click="player.prev()"><PlayerIcons name="prev" :stroke="1.3" /></button>
      <button type="button" class="grid size-12 place-items-center" :aria-label="player.playing ? t('player.pause') : t('player.play')" @click="player.toggle()">
        <PlayerIcons :name="player.playing ? 'pause' : 'play'" :size="28" :stroke="1.6" />
      </button>
      <button type="button" class="grid size-11 place-items-center" :aria-label="t('player.next')" @click="player.next()"><PlayerIcons name="next" :stroke="1.3" /></button>
    </div>
    <div class="flex min-w-0 flex-1 flex-col justify-center">
      <!-- the line being sung (synced lyrics); click opens the lyrics -->
      <button
        type="button"
        class="h-[18px] truncate px-2 text-center text-[13px] transition-opacity xl:px-11"
        :class="lyrics.line ? 'text-accent hover:underline' : 'pointer-events-none opacity-0'"
        :tabindex="lyrics.line ? 0 : -1"
        :aria-label="t('player.showLyrics')"
        @click="openPlayer('lyrics')"
      >{{ lyrics.line || '·' }}</button>
      <div class="hidden items-center gap-2.5 font-display text-xs text-muted xl:flex">
        <span class="w-9 text-right">{{ duration(preview ?? player.currentTime) }}</span>
        <SeekBar :value="player.currentTime" :max="player.duration" :label="t('player.seek')" @change="player.seek" @preview="(v) => (preview = v)" />
        <span class="w-9">{{ duration(player.duration) }}</span>
      </div>
      <span class="text-center font-display text-xs text-muted xl:hidden">{{ duration(preview ?? player.currentTime) }} / {{ duration(player.duration) }}</span>
    </div>
    <!-- narrow PC windows: the seek bar runs along the bottom edge instead -->
    <div class="absolute inset-x-10 -bottom-1.5 xl:hidden">
      <SeekBar :value="player.currentTime" :max="player.duration" :label="t('player.seek')" @change="player.seek" @preview="(v) => (preview = v)" />
    </div>
    <button v-if="ui.playerPrefs.showVolume" type="button" class="hidden size-10 place-items-center lg:grid" :aria-label="t('player.volume')" @click="player.volume = player.volume > 0 ? 0 : 1">
      <VolumeX v-if="player.volume === 0" :size="20" :stroke-width="1.3" />
      <Volume2 v-else :size="20" :stroke-width="1.3" />
    </button>
    <div v-if="ui.playerPrefs.showVolume" class="hidden w-20 lg:block">
      <SeekBar :value="player.volume" :max="1" :label="t('player.volume')" fill="var(--color-ink)" @change="(v) => (player.volume = v)" @preview="(v) => v !== null && (player.volume = v)" />
    </div>
    <button type="button" class="hidden size-10 place-items-center rounded-full hover:bg-surface xl:grid" :aria-label="t('player.lyrics')" :title="t('player.lyrics')" @click="openPlayer('lyrics')">
      <MicVocal :size="19" :stroke-width="1.3" />
    </button>
    <DevicesButton class="size-10" :size="19" />
    <button type="button" class="grid size-10 place-items-center rounded-full hover:bg-surface" :aria-label="t('player.queue')" :title="t('player.queue')" @click="openPlayer('queue')">
      <QueueIcon />
    </button>
    <button v-if="$route.name !== 'playing'" type="button" class="grid size-9 place-items-center rounded-full text-muted hover:bg-surface hover:text-ink" :aria-label="t('player.hideBar')" :title="t('player.hideBar')" @click="ui.barHidden = true">
      <ChevronDown :size="18" :stroke-width="1.6" />
    </button>
  </div>
</template>
