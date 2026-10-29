<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { ChevronDown, ChevronUp, EllipsisVertical, Heart, ListPlus } from '@lucide/vue'
import { coverUrl } from '../api'
import { duration } from '../format'
import { errorMessage } from '../i18n'
import { useLibrary } from '../stores/library'
import { usePlayer } from '../stores/player'
import { useUi } from '../stores/ui'
import CoverArt from './CoverArt.vue'
import PlayerControls from './PlayerControls.vue'
import QueueIcon from './QueueIcon.vue'
import SeekBar from './SeekBar.vue'

const { t } = useI18n()
const player = usePlayer()
const library = useLibrary()
const ui = useUi()
const preview = ref<number | null>(null)
const menu = ref(false)
const glow = ref('#C9D6E3')

async function fav() {
  if (!player.current) return
  try {
    await library.toggleFavorite(player.current)
  } catch (e) {
    ui.notify(errorMessage(e), true)
  }
}

// soft background tint from the album art's average colour
watch(
  () => player.current?.album_id,
  (albumId) => {
    glow.value = '#C9D6E3'
    if (!albumId || !player.current?.has_cover) return
    const img = new Image()
    img.onload = () => {
      const c = document.createElement('canvas')
      c.width = c.height = 8
      const ctx = c.getContext('2d')
      if (!ctx) return
      ctx.drawImage(img, 0, 0, 8, 8)
      const d = ctx.getImageData(0, 0, 8, 8).data
      let r = 0, g = 0, b = 0
      for (let i = 0; i < d.length; i += 4) (r += d[i]), (g += d[i + 1]), (b += d[i + 2])
      const n = d.length / 4
      glow.value = `rgb(${Math.round(r / n)} ${Math.round(g / n)} ${Math.round(b / n)})`
    }
    img.src = coverUrl(albumId, 'thumb')
  },
  { immediate: true },
)

// swipe down on the artwork to close
let startY: number | null = null
function touchStart(e: TouchEvent) {
  startY = e.touches[0].clientY
}
function touchEnd(e: TouchEvent) {
  if (startY !== null && e.changedTouches[0].clientY - startY > 90) ui.playerOpen = false
  startY = null
}
</script>

<template>
  <div
    v-if="player.current"
    role="dialog"
    aria-modal="true"
    :aria-label="t('player.nowPlaying')"
    class="fixed inset-0 z-50 overflow-y-auto bg-[#F7F6F2] text-ink"
  >
    <div class="relative mx-auto flex min-h-full max-w-md flex-col md:my-6 md:min-h-0 md:overflow-hidden md:rounded-3xl md:shadow-2xl">
      <div
        class="pointer-events-none absolute inset-x-[-80px] bottom-[-80px] top-[40%] opacity-50"
        :style="{ background: `radial-gradient(60% 45% at 15% 20%, ${glow} 0%, transparent 70%), radial-gradient(55% 40% at 95% 15%, ${glow} 0%, transparent 70%)` }"
      />

      <div class="relative" @touchstart.passive="touchStart" @touchend="touchEnd">
        <!-- full width, but capped on short screens so the controls stay visible -->
        <CoverArt :album-id="player.current.album_id" :has-cover="player.current.has_cover" size="large" rounded="rounded-none" class="mx-auto w-full max-w-[min(100%,50dvh)]" />
        <button
          type="button"
          class="absolute right-3 grid size-11 place-items-center rounded-full bg-white/70 backdrop-blur"
          style="top: calc(env(safe-area-inset-top) + 10px)"
          :aria-label="t('player.close')"
          @click="ui.playerOpen = false"
        >
          <ChevronDown :size="24" :stroke-width="1.4" />
        </button>
      </div>

      <div class="relative -mt-3">
        <SeekBar :value="player.currentTime" :max="player.duration" :label="t('player.seek')" track="rgb(17 17 19 / 0.12)" @change="player.seek" @preview="(v) => (preview = v)" />
      </div>

      <div class="pb-safe relative flex flex-1 flex-col px-5 pb-6">
        <div class="flex justify-between font-display text-sm text-[#52525B]">
          <span>{{ duration(preview ?? player.currentTime) }}</span>
          <span>{{ duration(player.duration) }}</span>
        </div>

        <div class="mt-1 flex items-center justify-between">
          <button type="button" class="grid size-11 place-items-center" :aria-label="t('common.addToPlaylist')" @click="ui.playlistPicker = [player.current]">
            <ListPlus :size="24" :stroke-width="1.3" />
          </button>
          <button
            type="button"
            class="grid size-11 place-items-center"
            :class="library.isFavorite(player.current) ? 'text-accent' : ''"
            :aria-label="library.isFavorite(player.current) ? t('common.favoriteRemove') : t('common.favoriteAdd')"
            @click="fav"
          >
            <Heart :size="26" :stroke-width="1.3" :fill="library.isFavorite(player.current) ? 'currentColor' : 'none'" />
          </button>
          <div class="relative">
            <button type="button" class="grid size-11 place-items-center" :aria-label="t('common.moreActions')" @click="menu = !menu">
              <EllipsisVertical :size="22" :stroke-width="1.3" />
            </button>
            <div v-if="menu" class="absolute bottom-12 right-0 z-10 flex w-52 flex-col overflow-hidden rounded-2xl border border-line bg-bg py-1.5 text-[15px] shadow-xl">
              <RouterLink v-if="player.current.album_id" :to="{ name: 'album', params: { id: player.current.album_id } }" class="px-4 py-3 hover:bg-surface" @click="(menu = false), (ui.playerOpen = false)">{{ t('common.goToAlbum') }}</RouterLink>
              <RouterLink v-if="player.current.artist_id" :to="{ name: 'artist', params: { id: player.current.artist_id } }" class="px-4 py-3 hover:bg-surface" @click="(menu = false), (ui.playerOpen = false)">{{ t('common.goToArtist') }}</RouterLink>
            </div>
          </div>
        </div>

        <div class="mt-3 flex flex-col items-center gap-1 text-center">
          <span class="line-clamp-2 text-2xl font-medium">{{ player.current.title }}</span>
          <span class="text-[17px] font-light text-[#52525B]">{{ player.current.artist || t('common.unknownArtist') }}</span>
        </div>

        <div class="mt-6"><PlayerControls large /></div>

        <div class="mt-auto flex items-center justify-between pt-4">
          <span class="w-11 font-display text-[13px] uppercase text-[#52525B]">{{ player.current.format }}</span>
          <button type="button" class="flex h-11 items-center gap-1.5 px-3 text-[15px]" @click="ui.queueOpen = true">
            {{ t('player.upNextButton') }} <ChevronUp :size="16" :stroke-width="1.6" />
          </button>
          <button type="button" class="grid size-11 place-items-center" :aria-label="t('player.queue')" @click="ui.queueOpen = true">
            <QueueIcon />
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
