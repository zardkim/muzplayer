<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { Heart, ListMusic, Pause, Play, Volume2, VolumeX } from '@lucide/vue'
import { duration } from '../format'
import { errorMessage } from '../i18n'
import { useLibrary } from '../stores/library'
import { usePlayer } from '../stores/player'
import { useUi } from '../stores/ui'
import CoverArt from './CoverArt.vue'
import PlayerControls from './PlayerControls.vue'
import SeekBar from './SeekBar.vue'

const { t } = useI18n()
const player = usePlayer()
const library = useLibrary()
const ui = useUi()

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
  <template v-if="player.current">
    <!-- desktop -->
    <footer
      :aria-label="t('player.nowPlaying')"
      class="hidden min-h-[88px] flex-wrap items-center gap-x-8 gap-y-2 border-t border-line bg-player px-6 py-3 md:flex"
    >
      <div class="flex min-w-0 flex-[1_1_260px] items-center gap-3.5">
        <button type="button" class="size-14 flex-none" :aria-label="t('player.open')" @click="ui.playerOpen = true">
          <CoverArt :album-id="player.current.album_id" :has-cover="player.current.has_cover" rounded="rounded-lg" />
        </button>
        <div class="flex min-w-0 flex-col">
          <span class="truncate text-[15px] font-semibold">{{ player.current.title }}</span>
          <RouterLink
            v-if="player.current.artist_id"
            :to="{ name: 'artist', params: { id: player.current.artist_id } }"
            class="truncate text-[13px] text-muted hover:text-ink"
          >{{ player.current.artist }}</RouterLink>
          <span v-else class="truncate text-[13px] text-muted">{{ player.current.artist || t('common.unknownArtist') }}</span>
        </div>
        <button
          type="button"
          class="grid size-11 flex-none place-items-center"
          :class="library.isFavorite(player.current) ? 'text-accent' : 'text-subtle hover:text-ink'"
          :aria-label="library.isFavorite(player.current) ? t('common.favoriteRemove') : t('common.favoriteAdd')"
          @click="fav"
        >
          <Heart :size="20" :fill="library.isFavorite(player.current) ? 'currentColor' : 'none'" />
        </button>
      </div>
      <div class="flex flex-[2_1_420px] flex-col items-center gap-1">
        <PlayerControls />
        <div class="flex w-full max-w-[560px] items-center gap-2.5 font-display text-xs text-muted">
          <span class="w-10 text-right">{{ duration(player.currentTime) }}</span>
          <SeekBar :value="player.currentTime" :max="player.duration" :label="t('player.seek')" @change="player.seek" />
          <span class="w-10">{{ duration(player.duration) }}</span>
        </div>
      </div>
      <div class="flex flex-[1_1_200px] items-center justify-end gap-2 text-muted">
        <button
          type="button"
          class="grid size-11 place-items-center hover:text-ink"
          :class="ui.queueOpen ? 'text-accent' : ''"
          :aria-label="t('player.queue')"
          :aria-pressed="ui.queueOpen"
          @click="ui.queueOpen = !ui.queueOpen"
        >
          <ListMusic :size="20" />
        </button>
        <button
          type="button"
          class="grid size-11 place-items-center hover:text-ink"
          :aria-label="t('player.volume')"
          @click="player.volume = player.volume > 0 ? 0 : 1"
        >
          <VolumeX v-if="player.volume === 0" :size="20" />
          <Volume2 v-else :size="20" />
        </button>
        <div class="w-24">
          <SeekBar :value="player.volume" :max="1" :label="t('player.volume')" fill="#F2EFE9" @change="(v) => (player.volume = v)" />
        </div>
      </div>
    </footer>

    <!-- mobile mini player -->
    <div class="mx-2 mb-1 flex flex-col gap-2 rounded-2xl bg-surface-2 p-2 md:hidden">
      <div class="flex items-center gap-3">
        <button type="button" class="flex min-w-0 flex-1 items-center gap-3 text-left" :aria-label="t('player.open')" @click="ui.playerOpen = true">
          <CoverArt :album-id="player.current.album_id" :has-cover="player.current.has_cover" rounded="rounded-lg" class="size-11 flex-none" />
          <span class="flex min-w-0 flex-col">
            <span class="truncate text-sm font-semibold">{{ player.current.title }}</span>
            <span class="truncate text-xs text-muted">{{ player.current.artist || t('common.unknownArtist') }}</span>
          </span>
        </button>
        <button
          type="button"
          class="grid size-11 place-items-center"
          :class="library.isFavorite(player.current) ? 'text-accent' : 'text-subtle'"
          :aria-label="library.isFavorite(player.current) ? t('common.favoriteRemove') : t('common.favoriteAdd')"
          @click="fav"
        >
          <Heart :size="20" :fill="library.isFavorite(player.current) ? 'currentColor' : 'none'" />
        </button>
        <button type="button" class="grid size-11 place-items-center" :aria-label="player.playing ? t('player.pause') : t('player.play')" @click="player.toggle()">
          <Pause v-if="player.playing" :size="22" fill="currentColor" />
          <Play v-else :size="22" fill="currentColor" />
        </button>
      </div>
      <div class="h-0.5 rounded-full bg-line-strong">
        <div class="h-0.5 rounded-full bg-accent" :style="{ width: player.duration ? `${(player.currentTime / player.duration) * 100}%` : '0%' }" />
      </div>
    </div>
  </template>
</template>
