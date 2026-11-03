<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { Disc3, Heart, ListPlus, MonitorPlay, UserRound } from '@lucide/vue'
import { errorMessage } from '../i18n'
import { useLibrary } from '../stores/library'
import { usePlayer } from '../stores/player'
import { useUi } from '../stores/ui'
import StarRating from './StarRating.vue'

// The phone player's ••• menu, a frosted card by the button: the song's quick actions in a row on
// top (like, add to a playlist, its videos), then where to go (album, artist), then its stars.
// `up`: it opens above the button (the button is low on the screen).
defineProps<{ up?: boolean }>()
const emit = defineEmits<{ close: [] }>()
const { t } = useI18n()
const player = usePlayer()
const library = useLibrary()
const ui = useUi()

function done() {
  emit('close')
}
async function like() {
  if (!player.current) return
  try {
    await library.toggleFavorite(player.current)
  } catch (e) {
    ui.notify(errorMessage(e), true)
  }
}
async function rate(stars: number | null) {
  if (!player.current) return
  try {
    await library.rate(player.current, stars)
  } catch (e) {
    ui.notify(errorMessage(e), true)
  }
}
</script>

<template>
  <!-- a tap anywhere else closes it -->
  <div class="fixed inset-0 z-20" aria-hidden="true" @click="done" />
  <div
    v-if="player.current"
    role="menu"
    class="absolute right-0 z-30 flex w-[min(19rem,calc(100vw-32px))] origin-top-right flex-col overflow-hidden rounded-[28px] border border-white/10 bg-[rgb(52_52_56/0.82)] text-[16px] shadow-2xl backdrop-blur-xl"
    :class="up ? 'bottom-full mb-2 origin-bottom-right' : 'top-full mt-2'"
  >
    <div class="grid grid-cols-3 gap-1 px-2 pb-3 pt-4 text-center text-[13px] leading-tight break-keep">
      <button type="button" role="menuitem" class="flex flex-col items-center gap-1.5" @click="like">
        <Heart :size="24" :stroke-width="1.6" :fill="library.isFavorite(player.current) ? 'currentColor' : 'none'" :class="library.isFavorite(player.current) ? 'text-like' : ''" />
        {{ library.isFavorite(player.current) ? t('common.favoriteRemove') : t('common.favoriteAdd') }}
      </button>
      <button type="button" role="menuitem" class="flex flex-col items-center gap-1.5" @click="(ui.playlistPicker = [player.current]), done()">
        <ListPlus :size="24" :stroke-width="1.6" />{{ t('common.addToPlaylist') }}
      </button>
      <button
        type="button"
        role="menuitem"
        class="flex flex-col items-center gap-1.5 disabled:opacity-35"
        :disabled="!player.current.has_video"
        @click="(ui.videoTarget = { trackId: player.current.id, title: player.current.title, artist: player.current.artist }), done()"
      >
        <MonitorPlay :size="24" :stroke-width="1.6" />{{ t('common.watchVideos') }}
      </button>
    </div>
    <div class="mx-5 border-t border-white/12" />
    <RouterLink
      v-if="player.current.album_id && player.current.album_kind !== 'chart'"
      role="menuitem"
      :to="{ name: 'album', params: { id: player.current.album_id } }"
      class="flex items-center gap-4 px-5 py-3.5 hover:bg-white/5"
      @click="done"
    ><Disc3 :size="22" :stroke-width="1.5" />{{ t('common.goToAlbum') }}</RouterLink>
    <RouterLink
      v-if="player.current.artist_id"
      role="menuitem"
      :to="{ name: 'artist', params: { id: player.current.artist_id } }"
      class="flex items-center gap-4 px-5 py-3.5 hover:bg-white/5"
      @click="done"
    ><UserRound :size="22" :stroke-width="1.5" />{{ t('common.goToArtist') }}</RouterLink>
    <div class="mx-5 border-t border-white/12" />
    <div class="flex items-center justify-between px-5 py-3.5">
      <span>{{ t('common.rating') }}</span>
      <StarRating :value="library.rating(player.current)" :size="20" @rate="rate" />
    </div>
  </div>
</template>
