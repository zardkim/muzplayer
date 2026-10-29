<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { ChevronDown, Heart, ListMusic, Plus } from '@lucide/vue'
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
  <div
    v-if="player.current"
    role="dialog"
    aria-modal="true"
    :aria-label="t('player.nowPlaying')"
    class="pb-safe fixed inset-0 z-40 overflow-y-auto bg-[#14202E]"
  >
    <div class="mx-auto flex min-h-full max-w-md flex-col gap-7 px-6 pb-8 pt-4">
      <div class="flex items-center justify-between">
        <button type="button" class="grid size-11 place-items-center" :aria-label="t('player.close')" @click="ui.playerOpen = false">
          <ChevronDown :size="26" />
        </button>
        <div class="flex min-w-0 flex-col items-center">
          <span class="text-[11px] tracking-widest text-muted">{{ t('player.nowPlaying') }}</span>
          <span class="truncate text-[13px] font-semibold">{{ player.current.album || t('common.unknownAlbum') }}</span>
        </div>
        <span class="size-11" />
      </div>

      <CoverArt
        :album-id="player.current.album_id"
        :has-cover="player.current.has_cover"
        size="large"
        rounded="rounded-[18px]"
        class="w-full shadow-[0_24px_60px_rgba(0,0,0,0.45)]"
      />

      <div class="flex items-center justify-between gap-3">
        <div class="flex min-w-0 flex-col gap-1">
          <span class="text-2xl font-bold tracking-tight">{{ player.current.title }}</span>
          <RouterLink
            v-if="player.current.artist_id"
            :to="{ name: 'artist', params: { id: player.current.artist_id } }"
            class="truncate text-base text-[#B7BCC5]"
            @click="ui.playerOpen = false"
          >{{ player.current.artist }}</RouterLink>
          <span v-else class="text-base text-[#B7BCC5]">{{ player.current.artist || t('common.unknownArtist') }}</span>
        </div>
        <button
          type="button"
          class="grid size-11 flex-none place-items-center"
          :class="library.isFavorite(player.current) ? 'text-accent' : 'text-[#B7BCC5]'"
          :aria-label="library.isFavorite(player.current) ? t('common.favoriteRemove') : t('common.favoriteAdd')"
          @click="fav"
        >
          <Heart :size="26" :fill="library.isFavorite(player.current) ? 'currentColor' : 'none'" />
        </button>
      </div>

      <div class="flex flex-col gap-1">
        <SeekBar :value="player.currentTime" :max="player.duration" :label="t('player.seek')" @change="player.seek" />
        <div class="flex justify-between font-display text-[13px] text-[#B7BCC5]">
          <span>{{ duration(player.currentTime) }}</span>
          <span>-{{ duration(Math.max(0, player.duration - player.currentTime)) }}</span>
        </div>
      </div>

      <PlayerControls large />

      <div class="mt-auto flex justify-between gap-3">
        <button type="button" class="flex h-11 items-center gap-2 rounded-full bg-ink/10 px-4 text-sm" @click="ui.playlistPicker = [player.current]">
          <Plus :size="18" />{{ t('common.addToPlaylist') }}
        </button>
        <button type="button" class="flex h-11 items-center gap-2 rounded-full bg-ink/10 px-4 text-sm" @click="ui.queueOpen = true">
          <ListMusic :size="18" />{{ t('player.queue') }}
        </button>
      </div>
    </div>
  </div>
</template>
