<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { ArrowDown, ArrowUp, EllipsisVertical, Flame, Heart, MonitorPlay, Star } from '@lucide/vue'
import { errorMessage } from '../i18n'
import { duration } from '../format'
import { useProgressive } from '../progressive'
import { useLibrary } from '../stores/library'
import { usePlayer } from '../stores/player'
import { useUi } from '../stores/ui'
import type { Track } from '../types'
import CoverArt from './CoverArt.vue'
import StarRating from './StarRating.vue'

const props = withDefaults(
  defineProps<{
    tracks: Track[]
    showCover?: boolean
    showAlbum?: boolean
    numbered?: boolean // show track_no instead of the list position
    ranked?: boolean // chart: show chart_position (list position when missing)
    editable?: boolean // playlist mode: remove / move up / move down
  }>(),
  { showCover: true, showAlbum: true },
)
const emit = defineEmits<{ remove: [index: number]; move: [index: number, dir: -1 | 1] }>()

const { t } = useI18n()
const player = usePlayer()
const library = useLibrary()
const ui = useUi()
// rows (i stays the index into props.tracks: play, select and the menu use the whole list)
const shown = useProgressive(() => props.tracks)
// row labels looked up once per list, not several times per row (a long list spent much of its time here)
const L = computed(() => ({
  select: t('common.select'), play: t('common.play'), videos: t('common.videos'), missing: t('common.missingFile'),
  unknownArtist: t('common.unknownArtist'), unknownAlbum: t('common.unknownAlbum'),
  favAdd: t('common.favoriteAdd'), popular: t('common.popular'), favRemove: t('common.favoriteRemove'), more: t('common.moreActions'),
}))
const menuOpen = ref<number | null>(null)
const menuUp = ref(false) // rows low on the screen open their menu upwards, clear of the player bar

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

async function rate(track: Track, stars: number | null) {
  try {
    await library.rate(track, stars)
  } catch (e) {
    ui.notify(errorMessage(e), true)
  }
}

function videos(track: Track) {
  menuOpen.value = null
  ui.videoTarget = { trackId: track.id, title: track.title, artist: track.artist }
}

const isCurrent = (track: Track) => player.current?.id === track.id

function openMenu(e: MouseEvent, i: number) {
  menuUp.value = (e.currentTarget as HTMLElement).getBoundingClientRect().top > window.innerHeight / 2
  menuOpen.value = menuOpen.value === i ? null : i
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
  <div class="flex flex-col">
    <!-- bulk action bar -->
    <div
      v-if="selected.size"
      class="sticky top-0 z-20 mb-2 hidden h-[52px] items-center gap-1 rounded-xl bg-ink pl-4 pr-2 text-sm text-on-ink md:flex"
    >
      <span class="flex-1">{{ t('common.selected', { n: selected.size }) }}</span>
      <button type="button" class="h-9 rounded-full px-3.5 hover:bg-on-ink/10" @click="bulk((x) => player.playTracks(x, 0))">{{ t('common.playSelected') }}</button>
      <button type="button" class="h-9 rounded-full px-3.5 hover:bg-on-ink/10" @click="bulk((x) => player.playNext(x))">{{ t('common.playNext') }}</button>
      <button type="button" class="h-9 rounded-full px-3.5 hover:bg-on-ink/10" @click="bulk((x) => player.addToQueue(x))">{{ t('common.addToQueue') }}</button>
      <button type="button" class="h-9 rounded-full px-3.5 hover:bg-on-ink/10" @click="bulk((x) => (ui.playlistPicker = x))">{{ t('common.addToPlaylist') }}</button>
      <button type="button" class="h-9 rounded-full bg-on-ink/15 px-3.5" @click="selected = new Set()">{{ t('common.clearSelection') }}</button>
    </div>

    <div v-if="tracks.length > 1" class="hidden h-10 items-center gap-3 border-b border-line px-2.5 text-[13px] text-muted md:flex">
      <input type="checkbox" class="size-[18px] accent-ink" :checked="allSelected" :aria-label="t('common.selectAll')" @change="toggleAll" />
      <span>{{ t('common.selectAll') }}</span>
    </div>

    <ol class="flex flex-col">
      <li
        v-for="(track, i) in shown"
        :key="`${track.id}-${i}`"
        class="group relative flex min-h-[68px] items-center gap-3 border-b border-surface md:px-2.5"
        :class="[
          // rows off screen skip layout and paint; not the one with its menu open (it would be clipped)
          menuOpen === i ? '' : '[contain-intrinsic-size:auto_69px] [content-visibility:auto]',
          isCurrent(track) ? 'bg-accent-soft' : selected.has(i) ? 'bg-surface' : 'md:hover:bg-surface/60',
          track.missing ? 'opacity-40' : '',
        ]"
      >
        <input
          type="checkbox"
          class="hidden size-[18px] flex-none accent-ink md:block"
          :checked="selected.has(i)"
          :aria-label="`${L.select}: ${track.title}`"
          @change="toggleSelect(i)"
        />
        <span
          v-if="!showCover || numbered || ranked"
          class="w-7 flex-none text-center font-display text-[15px]"
          :class="isCurrent(track) ? 'text-accent' : ranked ? 'font-medium text-ink' : 'text-muted'"
        >{{ ranked ? (track.chart_position ?? i + 1) : numbered ? (track.track_no ?? '–') : i + 1 }}</span>

        <button
          type="button"
          class="flex min-w-0 flex-1 items-center gap-3.5 py-1.5 text-left"
          :disabled="track.missing"
          :aria-label="`${L.play}: ${track.title}`"
          @click="play(i)"
        >
          <CoverArt v-if="showCover" :album-id="track.album_id" :has-cover="track.has_cover" :version="track.cover_v" rounded="rounded-md" class="size-[52px] flex-none" />
          <span class="flex min-w-0 flex-col">
            <span class="flex min-w-0 items-center gap-1.5">
              <span class="truncate text-[16px]" :class="isCurrent(track) ? 'font-medium text-accent' : ''">{{ track.title }}</span>
              <span v-if="track.popular && ui.playerPrefs.showPopular" class="flex flex-none items-center gap-0.5 rounded-full bg-accent-soft px-1.5 text-[11px] font-medium leading-[18px] text-accent"><Flame :size="11" :stroke-width="2" />{{ L.popular }}</span>
              <MonitorPlay v-if="track.has_video" :size="15" :stroke-width="1.5" class="flex-none text-muted" :aria-label="L.videos" />
            </span>
            <span class="truncate text-[14px] font-light text-muted">
              <template v-if="track.missing">{{ L.missing }}</template>
              <template v-else>{{ track.artist || L.unknownArtist }}<template v-if="showAlbum"> · {{ track.album || L.unknownAlbum }}</template></template>
            </span>
          </span>
        </button>

        <span class="hidden w-10 flex-none items-center gap-0.5 text-[13px] text-muted md:flex">
          <template v-if="library.rating(track)"><Star :size="13" fill="currentColor" class="text-accent" />{{ library.rating(track) }}</template>
        </span>
        <span class="hidden w-14 flex-none font-display text-[14px] text-muted md:block">{{ duration(track.duration) }}</span>

        <span class="flex flex-none items-center">
          <button
            type="button"
            class="grid size-11 place-items-center"
            :class="library.isFavorite(track) ? 'text-accent' : 'text-ink'"
            :aria-label="library.isFavorite(track) ? L.favRemove : L.favAdd"
            :aria-pressed="library.isFavorite(track)"
            @click="fav(track)"
          >
            <Heart :size="20" :stroke-width="1.3" :fill="library.isFavorite(track) ? 'currentColor' : 'none'" />
          </button>
          <span class="relative" data-track-menu>
            <button
              type="button"
              class="grid size-11 place-items-center text-ink"
              :aria-label="L.more"
              :aria-expanded="menuOpen === i"
              @click="(e) => openMenu(e, i)"
            >
              <EllipsisVertical :size="20" :stroke-width="1.3" />
            </button>
            <div
              v-if="menuOpen === i"
              class="absolute right-0 z-30 flex w-56 flex-col overflow-hidden rounded-2xl border border-line bg-bg py-1.5 text-[15px] shadow-xl"
              :class="menuUp ? 'bottom-11' : 'top-11'"
            >
              <template v-if="!track.missing">
                <StarRating :value="library.rating(track)" :size="18" class="px-2.5" @rate="(n) => rate(track, n)" />
                <div class="my-1 border-t border-line" />
                <button type="button" class="px-4 py-3 text-left hover:bg-surface" @click="action(() => player.playNext([track]))">{{ t('common.playNext') }}</button>
                <button type="button" class="px-4 py-3 text-left hover:bg-surface" @click="action(() => player.addToQueue([track]))">{{ t('common.addToQueue') }}</button>
                <button type="button" class="px-4 py-3 text-left hover:bg-surface" @click="action(() => (ui.playlistPicker = [track]))">{{ t('common.addToPlaylist') }}</button>
                <button type="button" class="px-4 py-3 text-left hover:bg-surface" @click="action(() => player.startRadio(track))">{{ t('common.startRadio') }}</button>
                <button type="button" class="px-4 py-3 text-left hover:bg-surface" @click="videos(track)">{{ t('common.watchVideos') }}</button>
              </template>
              <RouterLink v-if="track.album_id && track.album_kind !== 'chart'" :to="{ name: 'album', params: { id: track.album_id } }" class="px-4 py-3 hover:bg-surface" @click="menuOpen = null">{{ t('common.goToAlbum') }}</RouterLink>
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
