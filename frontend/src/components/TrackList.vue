<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { ArrowDown, ArrowUp, EllipsisVertical, Heart } from '@lucide/vue'
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

// ---- multi-select (checkbox column on wider screens) ----
const selected = ref(new Set<number>())
watch(() => props.tracks, () => selected.value.clear())
const selectedTracks = computed(() => props.tracks.filter((tr, i) => selected.value.has(i) && !tr.missing))
const allSelected = computed(() => props.tracks.length > 0 && selected.value.size === props.tracks.length)
function toggleSelect(i: number) {
  const s = new Set(selected.value)
  if (s.has(i)) s.delete(i)
  else s.add(i)
  selected.value = s
}
function toggleAll() {
  selected.value = allSelected.value ? new Set() : new Set(props.tracks.map((_, i) => i))
}
function bulk(fn: (tracks: Track[]) => void) {
  fn(selectedTracks.value)
  selected.value = new Set()
}

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

const isCurrent = (track: Track) => player.current?.id === track.id

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
  <div class="flex flex-col">
    <!-- bulk action bar -->
    <div
      v-if="selected.size"
      class="sticky top-0 z-20 mb-2 hidden h-[52px] items-center gap-1 rounded-xl bg-ink pl-4 pr-2 text-sm text-white md:flex"
    >
      <span class="flex-1">{{ t('common.selected', { n: selected.size }) }}</span>
      <button type="button" class="h-9 rounded-full px-3.5 hover:bg-white/10" @click="bulk((x) => player.playTracks(x, 0))">{{ t('common.playSelected') }}</button>
      <button type="button" class="h-9 rounded-full px-3.5 hover:bg-white/10" @click="bulk((x) => player.playNext(x))">{{ t('common.playNext') }}</button>
      <button type="button" class="h-9 rounded-full px-3.5 hover:bg-white/10" @click="bulk((x) => player.addToQueue(x))">{{ t('common.addToQueue') }}</button>
      <button type="button" class="h-9 rounded-full px-3.5 hover:bg-white/10" @click="bulk((x) => (ui.playlistPicker = x))">{{ t('common.addToPlaylist') }}</button>
      <button type="button" class="h-9 rounded-full bg-white/15 px-3.5" @click="selected = new Set()">{{ t('common.clearSelection') }}</button>
    </div>

    <div v-if="tracks.length > 1" class="hidden h-10 items-center gap-3 border-b border-line px-2.5 text-[13px] text-muted md:flex">
      <input type="checkbox" class="size-[18px] accent-ink" :checked="allSelected" :aria-label="t('common.selectAll')" @change="toggleAll" />
      <span>{{ t('common.selectAll') }}</span>
    </div>

    <ol class="flex flex-col">
      <li
        v-for="(track, i) in tracks"
        :key="`${track.id}-${i}`"
        class="group relative flex min-h-[68px] items-center gap-3 border-b border-surface md:px-2.5"
        :class="[
          isCurrent(track) ? 'bg-accent-soft' : selected.has(i) ? 'bg-surface' : 'md:hover:bg-surface/60',
          track.missing ? 'opacity-40' : '',
        ]"
      >
        <input
          type="checkbox"
          class="hidden size-[18px] flex-none accent-ink md:block"
          :checked="selected.has(i)"
          :aria-label="`${t('common.select')}: ${track.title}`"
          @change="toggleSelect(i)"
        />
        <span
          v-if="!showCover || numbered"
          class="w-7 flex-none text-center font-display text-[15px]"
          :class="isCurrent(track) ? 'text-accent' : 'text-muted'"
        >{{ numbered ? (track.track_no ?? '–') : i + 1 }}</span>

        <button
          type="button"
          class="flex min-w-0 flex-1 items-center gap-3.5 py-1.5 text-left"
          :disabled="track.missing"
          :aria-label="`${t('common.play')}: ${track.title}`"
          @click="play(i)"
        >
          <CoverArt v-if="showCover" :album-id="track.album_id" :has-cover="track.has_cover" rounded="rounded-md" class="size-[52px] flex-none" />
          <span class="flex min-w-0 flex-col">
            <span class="truncate text-[16px]" :class="isCurrent(track) ? 'font-medium text-accent' : ''">{{ track.title }}</span>
            <span class="truncate text-[14px] font-light text-muted">
              <template v-if="track.missing">{{ t('common.missingFile') }}</template>
              <template v-else>{{ track.artist || t('common.unknownArtist') }}<template v-if="showAlbum"> · {{ track.album || t('common.unknownAlbum') }}</template></template>
            </span>
          </span>
        </button>

        <span class="hidden w-14 flex-none font-display text-[14px] text-muted md:block">{{ duration(track.duration) }}</span>

        <span class="flex flex-none items-center">
          <button
            type="button"
            class="grid size-11 place-items-center"
            :class="library.isFavorite(track) ? 'text-accent' : 'text-ink'"
            :aria-label="library.isFavorite(track) ? t('common.favoriteRemove') : t('common.favoriteAdd')"
            :aria-pressed="library.isFavorite(track)"
            @click="fav(track)"
          >
            <Heart :size="20" :stroke-width="1.3" :fill="library.isFavorite(track) ? 'currentColor' : 'none'" />
          </button>
          <span class="relative" data-track-menu>
            <button
              type="button"
              class="grid size-11 place-items-center text-ink"
              :aria-label="t('common.moreActions')"
              :aria-expanded="menuOpen === i"
              @click="menuOpen = menuOpen === i ? null : i"
            >
              <EllipsisVertical :size="20" :stroke-width="1.3" />
            </button>
            <div
              v-if="menuOpen === i"
              class="absolute right-0 top-11 z-30 flex w-56 flex-col overflow-hidden rounded-2xl border border-line bg-bg py-1.5 text-[15px] shadow-xl"
            >
              <template v-if="!track.missing">
                <button type="button" class="px-4 py-3 text-left hover:bg-surface" @click="action(() => player.playNext([track]))">{{ t('common.playNext') }}</button>
                <button type="button" class="px-4 py-3 text-left hover:bg-surface" @click="action(() => player.addToQueue([track]))">{{ t('common.addToQueue') }}</button>
                <button type="button" class="px-4 py-3 text-left hover:bg-surface" @click="action(() => (ui.playlistPicker = [track]))">{{ t('common.addToPlaylist') }}</button>
              </template>
              <RouterLink v-if="track.album_id" :to="{ name: 'album', params: { id: track.album_id } }" class="px-4 py-3 hover:bg-surface" @click="menuOpen = null">{{ t('common.goToAlbum') }}</RouterLink>
              <RouterLink v-if="track.artist_id" :to="{ name: 'artist', params: { id: track.artist_id } }" class="px-4 py-3 hover:bg-surface" @click="menuOpen = null">{{ t('common.goToArtist') }}</RouterLink>
              <template v-if="editable">
                <div class="my-1 border-t border-line" />
                <button type="button" class="flex items-center gap-2 px-4 py-3 text-left hover:bg-surface disabled:opacity-40" :disabled="i === 0" @click="action(() => emit('move', i, -1))"><ArrowUp :size="16" />{{ t('common.moveUp') }}</button>
                <button type="button" class="flex items-center gap-2 px-4 py-3 text-left hover:bg-surface disabled:opacity-40" :disabled="i === tracks.length - 1" @click="action(() => emit('move', i, 1))"><ArrowDown :size="16" />{{ t('common.moveDown') }}</button>
                <button type="button" class="px-4 py-3 text-left text-danger hover:bg-surface" @click="action(() => emit('remove', i))">{{ t('common.remove') }}</button>
              </template>
            </div>
          </span>
        </span>
      </li>
    </ol>
  </div>
</template>
