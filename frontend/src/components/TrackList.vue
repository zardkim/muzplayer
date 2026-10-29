<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ArrowDown, ArrowUp, Ellipsis, Heart } from '@lucide/vue'
import { errorMessage } from '../i18n'
import { duration } from '../format'
import { useLibrary } from '../stores/library'
import { usePlayer } from '../stores/player'
import { useUi } from '../stores/ui'
import type { Track } from '../types'
import CoverArt from './CoverArt.vue'

const props = withDefaults(
  defineProps<{
    tracks: Track[]
    showCover?: boolean
    showAlbum?: boolean
    numbered?: boolean // show track_no instead of the list position
    editable?: boolean // playlist mode: remove / move up / move down
  }>(),
  { showCover: true, showAlbum: true },
)
const emit = defineEmits<{ remove: [index: number]; move: [index: number, dir: -1 | 1] }>()

const { t } = useI18n()
const player = usePlayer()
const library = useLibrary()
const ui = useUi()
const menuOpen = ref<number | null>(null)

function play(i: number) {
  if (props.tracks[i].missing) return
  player.playTracks(props.tracks, i)
}

async function fav(track: Track) {
  try {
    await library.toggleFavorite(track)
  } catch (e) {
    ui.notify(errorMessage(e), true)
  }
}

function isCurrent(track: Track) {
  return player.current?.id === track.id
}

function action(fn: () => void) {
  menuOpen.value = null
  fn()
}

function closeMenu(e: MouseEvent) {
  if (!(e.target as HTMLElement).closest('[data-track-menu]')) menuOpen.value = null
}
onMounted(() => document.addEventListener('click', closeMenu))
onUnmounted(() => document.removeEventListener('click', closeMenu))
</script>

<template>
  <ol class="flex flex-col">
    <li
      v-for="(track, i) in tracks"
      :key="`${track.id}-${i}`"
      class="group relative grid items-center gap-3 rounded-xl px-2 py-1.5 sm:px-3"
      :class="[
        showAlbum
          ? 'grid-cols-[28px_minmax(0,1fr)_auto] md:grid-cols-[28px_minmax(0,2fr)_minmax(0,1fr)_56px_auto]'
          : 'grid-cols-[28px_minmax(0,1fr)_auto] md:grid-cols-[28px_minmax(0,1fr)_56px_auto]',
        isCurrent(track) ? 'bg-surface-2' : 'hover:bg-surface',
        track.missing ? 'opacity-45' : '',
      ]"
    >
      <span class="text-center font-display text-sm" :class="isCurrent(track) ? 'text-accent' : 'text-muted'">
        <template v-if="isCurrent(track) && player.playing">
          <span class="inline-flex h-3.5 items-end gap-[2px]" aria-hidden="true">
            <span class="w-[3px] animate-pulse rounded-sm bg-accent" style="height: 60%" />
            <span class="w-[3px] animate-pulse rounded-sm bg-accent [animation-delay:200ms]" style="height: 100%" />
            <span class="w-[3px] animate-pulse rounded-sm bg-accent [animation-delay:400ms]" style="height: 45%" />
          </span>
        </template>
        <template v-else>{{ numbered ? (track.track_no ?? '–') : i + 1 }}</template>
      </span>

      <button
        type="button"
        class="flex min-w-0 items-center gap-3 py-1 text-left"
        :disabled="track.missing"
        :aria-label="`${t('common.play')}: ${track.title}`"
        @click="play(i)"
      >
        <CoverArt v-if="showCover" :album-id="track.album_id" :has-cover="track.has_cover" rounded="rounded-lg" class="size-11 flex-none" />
        <span class="flex min-w-0 flex-col">
          <span class="truncate text-[15px] font-semibold" :class="isCurrent(track) ? 'text-accent' : ''">{{ track.title }}</span>
          <span class="truncate text-[13px] text-muted">
            <template v-if="track.missing">{{ t('common.missingFile') }}</template>
            <template v-else>
              {{ track.artist || t('common.unknownArtist') }}<span v-if="showAlbum" class="md:hidden"> · {{ track.album || t('common.unknownAlbum') }}</span>
            </template>
          </span>
        </span>
      </button>

      <RouterLink
        v-if="showAlbum && track.album_id"
        :to="{ name: 'album', params: { id: track.album_id } }"
        class="hidden truncate text-[13px] text-muted hover:text-ink md:block"
      >{{ track.album || t('common.unknownAlbum') }}</RouterLink>
      <span v-else-if="showAlbum" class="hidden md:block" />

      <span class="hidden font-display text-[13px] text-muted md:block">{{ duration(track.duration) }}</span>

      <span class="flex items-center">
        <button
          type="button"
          class="grid size-11 place-items-center"
          :class="library.isFavorite(track) ? 'text-accent' : 'text-subtle hover:text-ink'"
          :aria-label="library.isFavorite(track) ? t('common.favoriteRemove') : t('common.favoriteAdd')"
          :aria-pressed="library.isFavorite(track)"
          @click="fav(track)"
        >
          <Heart :size="18" :fill="library.isFavorite(track) ? 'currentColor' : 'none'" />
        </button>
        <span class="relative" data-track-menu>
          <button
            type="button"
            class="grid size-11 place-items-center text-subtle hover:text-ink"
            :aria-label="t('common.moreActions')"
            :aria-expanded="menuOpen === i"
            @click="menuOpen = menuOpen === i ? null : i"
          >
            <Ellipsis :size="18" />
          </button>
          <div
            v-if="menuOpen === i"
            class="absolute right-0 top-11 z-30 flex w-52 flex-col overflow-hidden rounded-xl border border-line bg-surface-2 py-1 text-sm shadow-xl shadow-black/40"
          >
            <template v-if="!track.missing">
              <button type="button" class="px-4 py-2.5 text-left hover:bg-line" @click="action(() => player.playNext([track]))">{{ t('common.playNext') }}</button>
              <button type="button" class="px-4 py-2.5 text-left hover:bg-line" @click="action(() => player.addToQueue([track]))">{{ t('common.addToQueue') }}</button>
              <button type="button" class="px-4 py-2.5 text-left hover:bg-line" @click="action(() => (ui.playlistPicker = [track]))">{{ t('common.addToPlaylist') }}</button>
            </template>
            <RouterLink v-if="track.album_id" :to="{ name: 'album', params: { id: track.album_id } }" class="px-4 py-2.5 hover:bg-line" @click="menuOpen = null">{{ t('common.goToAlbum') }}</RouterLink>
            <RouterLink v-if="track.artist_id" :to="{ name: 'artist', params: { id: track.artist_id } }" class="px-4 py-2.5 hover:bg-line" @click="menuOpen = null">{{ t('common.goToArtist') }}</RouterLink>
            <template v-if="editable">
              <div class="my-1 border-t border-line" />
              <button type="button" class="flex items-center gap-2 px-4 py-2.5 text-left hover:bg-line disabled:opacity-40" :disabled="i === 0" @click="action(() => emit('move', i, -1))"><ArrowUp :size="16" />{{ t('common.moveUp') }}</button>
              <button type="button" class="flex items-center gap-2 px-4 py-2.5 text-left hover:bg-line disabled:opacity-40" :disabled="i === tracks.length - 1" @click="action(() => emit('move', i, 1))"><ArrowDown :size="16" />{{ t('common.moveDown') }}</button>
              <button type="button" class="px-4 py-2.5 text-left text-danger hover:bg-line" @click="action(() => emit('remove', i))">{{ t('common.remove') }}</button>
            </template>
          </div>
        </span>
      </span>
    </li>
  </ol>
</template>
