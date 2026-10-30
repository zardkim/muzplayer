<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { Heart, Volume2, VolumeX } from '@lucide/vue'
import { duration } from '../format'
import { errorMessage } from '../i18n'
import { useLibrary } from '../stores/library'
import { usePlayer } from '../stores/player'
import { useUi } from '../stores/ui'
import BookCover from './BookCover.vue'
import CoverArt from './CoverArt.vue'
import PlayerIcons from './PlayerIcons.vue'
import QueueIcon from './QueueIcon.vue'
import SeekBar from './SeekBar.vue'
import SkipIcon from './SkipIcon.vue'

// Desktop: floating pill at the bottom of the content column.
// Phone: floating mini player above the tab bar (see App.vue for placement).
defineProps<{ mobile?: boolean }>()
const { t } = useI18n()
const player = usePlayer()
const library = useLibrary()
const ui = useUi()
const preview = ref<number | null>(null)

const isBook = computed(() => player.mode === 'book' && !!player.book)
const segLength = computed(() => Math.max(0, player.segment.end - player.segment.start))
const segPos = computed(() => Math.min(segLength.value, Math.max(0, player.bookPos - player.segment.start)))

async function fav() {
  if (!player.current) return
  try {
    await library.toggleFavorite(player.current)
  } catch (e) {
    ui.notify(errorMessage(e), true)
  }
}
</script>

<template>
  <!-- phone mini player -->
  <div v-if="mobile" class="glass relative flex h-[60px] items-center gap-3 overflow-hidden rounded-full pl-2 pr-1.5">
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
      <span class="absolute inset-x-6 bottom-0 h-[2px] bg-line">
        <span class="block h-full bg-accent" :style="{ width: player.book.duration ? `${(player.bookPos / player.book.duration) * 100}%` : '0%' }" />
      </span>
    </template>
    <template v-else-if="player.current">
      <button type="button" class="flex min-w-0 flex-1 items-center gap-3 text-left" :aria-label="t('player.open')" @click="ui.playerOpen = true">
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
      <span class="absolute inset-x-6 bottom-0 h-[2px] bg-line">
        <span class="block h-full bg-accent" :style="{ width: player.duration ? `${(player.currentTime / player.duration) * 100}%` : '0%' }" />
      </span>
    </template>
    <template v-else>
      <span class="flex-1 pl-3 text-[15px] font-light text-muted">{{ t('player.notPlaying') }}</span>
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
      <SeekBar :value="player.volume" :max="1" :label="t('player.volume')" fill="#111113" @change="(v) => (player.volume = v)" @preview="(v) => v !== null && (player.volume = v)" />
    </div>
  </div>

  <!-- desktop floating player -->
  <div v-else-if="player.current" :aria-label="t('player.nowPlaying')" class="glass flex h-[76px] items-center gap-4 rounded-full px-3.5">
    <button type="button" class="size-[52px] flex-none" :aria-label="t('player.open')" @click="ui.playerOpen = true">
      <CoverArt :album-id="player.current.album_id" :has-cover="player.current.has_cover" :version="player.current.cover_v" rounded="rounded-full" />
    </button>
    <div class="flex w-52 min-w-0 flex-col">
      <span class="truncate text-[15px]">{{ player.current.title }}</span>
      <RouterLink
        v-if="player.current.artist_id"
        :to="{ name: 'artist', params: { id: player.current.artist_id } }"
        class="truncate text-[13px] font-light text-muted hover:text-ink"
      >{{ player.current.artist }}</RouterLink>
      <span v-else class="truncate text-[13px] font-light text-muted">{{ player.current.artist || t('common.unknownArtist') }}</span>
    </div>
    <button
      type="button"
      class="grid size-10 flex-none place-items-center"
      :class="library.isFavorite(player.current) ? 'text-accent' : 'text-ink'"
      :aria-label="library.isFavorite(player.current) ? t('common.favoriteRemove') : t('common.favoriteAdd')"
      @click="fav"
    >
      <Heart :size="20" :stroke-width="1.3" :fill="library.isFavorite(player.current) ? 'currentColor' : 'none'" />
    </button>
    <div class="flex items-center">
      <button type="button" class="grid size-11 place-items-center" :aria-label="t('player.prev')" @click="player.prev()"><PlayerIcons name="prev" :stroke="1.3" /></button>
      <button type="button" class="grid size-12 place-items-center" :aria-label="player.playing ? t('player.pause') : t('player.play')" @click="player.toggle()">
        <PlayerIcons :name="player.playing ? 'pause' : 'play'" :size="28" :stroke="1.6" />
      </button>
      <button type="button" class="grid size-11 place-items-center" :aria-label="t('player.next')" @click="player.next()"><PlayerIcons name="next" :stroke="1.3" /></button>
    </div>
    <div class="flex min-w-0 flex-1 items-center gap-2.5 font-display text-xs text-muted">
      <span class="w-9 text-right">{{ duration(preview ?? player.currentTime) }}</span>
      <SeekBar :value="player.currentTime" :max="player.duration" :label="t('player.seek')" @change="player.seek" @preview="(v) => (preview = v)" />
      <span class="w-9">{{ duration(player.duration) }}</span>
    </div>
    <button type="button" class="grid size-10 place-items-center" :aria-label="t('player.volume')" @click="player.volume = player.volume > 0 ? 0 : 1">
      <VolumeX v-if="player.volume === 0" :size="20" :stroke-width="1.3" />
      <Volume2 v-else :size="20" :stroke-width="1.3" />
    </button>
    <div class="w-20">
      <SeekBar :value="player.volume" :max="1" :label="t('player.volume')" fill="#111113" @change="(v) => (player.volume = v)" @preview="(v) => v !== null && (player.volume = v)" />
    </div>
    <button
      type="button"
      class="grid size-11 place-items-center"
      :class="ui.queueOpen ? 'text-accent' : ''"
      :aria-label="t('player.queue')"
      :aria-pressed="ui.queueOpen"
      @click="ui.queueOpen = !ui.queueOpen"
    >
      <QueueIcon />
    </button>
  </div>
</template>
