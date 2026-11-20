<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { AudioLines, ChevronDown, Disc3, EllipsisVertical, Heart, ImagePlus, Info, ListPlus, Music2, Pencil, Play, Tag, Trash2, Unlink } from '@lucide/vue'
import { api } from '../api'
import { errorMessage } from '../i18n'
import { useUi } from '../stores/ui'
import { type VideoKind, type VideoListItem } from '../types'
import { kindKeys, kindName, loadVideoKinds } from '../videoKinds'
import CoverArt from './CoverArt.vue'
import InlineVideo from './InlineVideo.vue'
import VideoInfoSheet from './VideoInfoSheet.vue'
import VideoThumb from './VideoThumb.vue'
import YoutubeIcon from './YoutubeIcon.vue'

// One music video in a grid: its picture plays it there (InlineVideo; ⤢ there: the large player). Under the title: like it, its kind (who added it,
// or an admin, may change it), put it in a video playlist. The ⋮ menu: a NAS file's title,
// thumbnail (another scene) and song (picked from a search), and removing it.
const props = defineProps<{ video: VideoListItem }>()
const emit = defineEmits<{ play: []; changed: []; liked: [boolean]; extract: [] }>()
const { t } = useI18n()
const ui = useUi()
const menu = ref(false)
const infoOpen = ref(false) // its details (VideoInfoSheet)
loadVideoKinds()
const kindMenu = ref(false)
const liked = ref(!!props.video.is_favorite)
async function like() {
  const on = !liked.value
  liked.value = on
  try {
    await api(`/videos/${props.video.id}/favorite`, { method: on ? 'PUT' : 'DELETE' })
    emit('liked', on)
  } catch (e) {
    liked.value = !on
    ui.notify(errorMessage(e), true)
  }
}
const menuUp = ref(false) // cards low on the screen open their menu upwards
function toggleMenu(e: MouseEvent) {
  menuUp.value = (e.currentTarget as HTMLElement).getBoundingClientRect().top > window.innerHeight / 2
  menu.value = !menu.value
}

async function setKind(kind: VideoKind) {
  kindMenu.value = false
  try {
    await api(`/videos/${props.video.id}`, { method: 'PATCH', body: { kind } })
    emit('changed')
  } catch (e) {
    ui.notify(errorMessage(e), true)
  }
}
async function rename() {
  menu.value = false
  const title = prompt(t('videos.renameVideo'), props.video.title)?.trim()
  if (!title || title === props.video.title) return
  try {
    await api(`/videos/${props.video.id}`, { method: 'PATCH', body: { title } })
    emit('changed')
  } catch (e) {
    ui.notify(errorMessage(e), true)
  }
}
const remaking = ref(false)
async function remakeThumb() {
  menu.value = false
  remaking.value = true
  try {
    await api(`/videos/${props.video.id}/thumb`, { method: 'POST' })
    ui.thumbBust = { ...ui.thumbBust, [props.video.id]: Date.now() }
    ui.notify(t('videos.thumbMade'))
  } catch (e) {
    ui.notify(errorMessage(e), true)
  } finally {
    remaking.value = false
  }
}
// its song or album: picked from a search (the link sheet, App.vue), or let go
function pickLink(tab: 'track' | 'album') {
  menu.value = false
  ui.videoLinkTab = tab
  ui.videoLink = props.video
}
async function unlink() {
  menu.value = false
  try {
    await api<VideoListItem>(`/videos/${props.video.id}/link`, { method: 'POST', body: {} })
    ui.notify(t('videos.unlinked'))
    emit('changed')
  } catch (e) {
    ui.notify(errorMessage(e), true)
  }
}
async function remove() {
  menu.value = false
  if (!confirm(t('videos.removeConfirm', { title: props.video.title }))) return
  try {
    await api(`/videos/${props.video.id}`, { method: 'DELETE' })
    emit('changed')
  } catch (e) {
    ui.notify(errorMessage(e), true)
  }
}
function outside(e: MouseEvent) {
  if (!(e.target as HTMLElement).closest('[data-video-menu]')) menu.value = false
  if (!(e.target as HTMLElement).closest('[data-kind-menu]')) kindMenu.value = false
}
onMounted(() => document.addEventListener('click', outside))
onUnmounted(() => document.removeEventListener('click', outside))
</script>

<template>
  <div class="flex flex-col gap-2.5">
    <InlineVideo v-if="ui.inlineVideo === video.id" :video="video" @expand="(ui.inlineVideo = null), emit('play')" />
    <!-- content-visibility: off the screen its picture isn't drawn (a long page scrolls lighter on a phone) -->
    <button v-else type="button" class="group relative aspect-video overflow-hidden rounded-xl bg-surface [content-visibility:auto]" :aria-label="`${t('videos.play')}: ${video.title}`" @click="ui.inlineVideo = video.id">
      <VideoThumb :video="video" :icon="40" />
      <span v-if="remaking" class="absolute inset-0 grid place-items-center bg-black/50 text-[13px] text-white">{{ t('videos.thumbMaking') }}</span>
      <span class="absolute inset-0 m-auto grid size-12 place-items-center rounded-full bg-black/55 text-white"><Play :size="20" fill="currentColor" /></span>
      <span class="absolute left-2 top-2 flex h-5 items-center rounded-full bg-black/60 px-2 text-[11px] text-white">
        <YoutubeIcon v-if="video.youtube_id" :size="15" /><template v-else>{{ t('videos.nas') }}</template>
      </span>
    </button>
    <div class="flex items-start gap-1">
      <span class="line-clamp-2 min-w-0 flex-1 text-[15px] leading-snug">{{ video.title }}</span>
      <span class="relative -mr-2 -mt-1.5" data-video-menu>
        <button type="button" class="grid size-9 place-items-center text-muted hover:text-ink" :aria-label="t('common.moreActions')" :aria-expanded="menu" @click="toggleMenu">
          <EllipsisVertical :size="18" :stroke-width="1.4" />
        </button>
        <div v-if="menu" class="absolute right-0 z-30 flex w-56 flex-col overflow-hidden rounded-2xl border border-line bg-bg py-1.5 text-[14px] shadow-xl" :class="menuUp ? 'bottom-9' : 'top-9'">
          <!-- its details: everyone -->
          <button type="button" class="flex items-center gap-3 px-4 py-2.5 text-left hover:bg-surface" @click="(menu = false), (infoOpen = true)"><Info :size="16" :stroke-width="1.6" class="flex-none text-muted" />{{ t('videoInfo.menu') }}</button>
          <template v-if="video.can_edit">
            <div class="my-1 border-t border-line" />
            <!-- NAS files: their title, thumbnail and song are ours to change -->
            <template v-if="video.file_path">
              <button type="button" class="flex items-center gap-3 px-4 py-2.5 text-left hover:bg-surface" @click="rename"><Pencil :size="16" :stroke-width="1.6" class="flex-none text-muted" />{{ t('videos.renameVideo') }}</button>
              <button type="button" class="flex items-center gap-3 px-4 py-2.5 text-left hover:bg-surface" :disabled="remaking" @click="remakeThumb"><ImagePlus :size="16" :stroke-width="1.6" class="flex-none text-muted" />{{ t('videos.remakeThumb') }}</button>
            </template>
            <!-- its song or album -->
            <button type="button" class="flex items-center gap-3 px-4 py-2.5 text-left hover:bg-surface" @click="pickLink('track')"><Music2 :size="16" :stroke-width="1.6" class="flex-none text-muted" />{{ t('videos.linkSong') }}</button>
            <button type="button" class="flex items-center gap-3 px-4 py-2.5 text-left hover:bg-surface" @click="pickLink('album')"><Disc3 :size="16" :stroke-width="1.6" class="flex-none text-muted" />{{ t('videos.linkAlbum') }}</button>
            <button v-if="video.track_id || video.album_id" type="button" class="flex items-center gap-3 px-4 py-2.5 text-left hover:bg-surface" @click="unlink"><Unlink :size="16" :stroke-width="1.6" class="flex-none text-muted" />{{ t('videos.unlink') }}</button>
            <div class="my-1 border-t border-line" />
            <!-- its sound as a song (extract.py) -->
            <button type="button" class="flex items-center gap-3 px-4 py-2.5 text-left hover:bg-surface" @click="(menu = false), emit('extract')"><AudioLines :size="16" :stroke-width="1.6" class="flex-none text-muted" />{{ t('extract.menu') }}</button>
            <div class="my-1 border-t border-line" />
            <button type="button" class="flex items-center gap-3 px-4 py-2.5 text-left hover:bg-surface text-danger" @click="remove"><Trash2 :size="16" :stroke-width="1.6" class="flex-none" />{{ t('videos.remove') }}</button>
          </template>
        </div>
      </span>
    </div>
    <!-- like, kind, video playlist -->
    <div class="-ml-2 -mt-1 flex items-center gap-0.5">
      <button
        type="button"
        class="grid size-9 place-items-center rounded-full hover:bg-surface"
        :class="liked ? 'text-like' : 'text-muted hover:text-ink'"
        :aria-label="liked ? t('common.favoriteRemove') : t('common.favoriteAdd')"
        :aria-pressed="liked"
        :title="liked ? t('common.favoriteRemove') : t('common.favoriteAdd')"
        @click="like"
      >
        <Heart :size="18" :stroke-width="1.5" :fill="liked ? 'currentColor' : 'none'" />
      </button>
      <span class="relative" data-kind-menu>
        <button
          type="button"
          class="flex h-8 items-center gap-1 rounded-full px-2.5 text-[13px] text-muted"
          :class="video.can_edit ? 'hover:bg-surface hover:text-ink' : 'cursor-default'"
          :aria-label="`${t('videos.kind')}: ${kindName(video.kind)}`"
          :title="video.can_edit ? t('videos.changeKind') : t('videos.kind')"
          :aria-expanded="video.can_edit ? kindMenu : undefined"
          @click="video.can_edit && (kindMenu = !kindMenu)"
        >
          <Tag :size="15" :stroke-width="1.5" />{{ kindName(video.kind) }}<ChevronDown v-if="video.can_edit" :size="14" :stroke-width="1.5" />
        </button>
        <div v-if="kindMenu" class="absolute left-0 top-9 z-30 flex w-40 flex-col overflow-hidden rounded-2xl border border-line bg-bg py-1.5 text-[14px] shadow-xl">
          <button
            v-for="k in kindKeys"
            :key="k"
            type="button"
            class="px-4 py-2 text-left hover:bg-surface"
            :class="video.kind === k ? 'font-medium text-accent' : ''"
            :disabled="video.kind === k"
            @click="setKind(k)"
          >{{ kindName(k) }}</button>
        </div>
      </span>
      <button type="button" class="grid size-9 place-items-center rounded-full text-muted hover:bg-surface hover:text-ink" :aria-label="t('videos.addToPlaylist')" :title="t('videos.addToPlaylist')" @click="ui.videoPick = [video]">
        <ListPlus :size="18" :stroke-width="1.5" />
      </button>
    </div>
    <RouterLink
      v-if="video.target?.album_id"
      :to="{ name: 'album', params: { id: video.target.album_id } }"
      class="flex min-w-0 items-center gap-2.5 text-[13px] text-muted hover:text-ink"
    >
      <CoverArt :album-id="video.target.album_id" :has-cover="video.target.has_cover" :version="video.target.cover_v" rounded="rounded" class="size-8 flex-none" />
      <span class="flex min-w-0 flex-col">
        <span class="truncate text-ink">{{ video.target.title }}</span>
        <span class="truncate">{{ video.target.type === 'track' ? t('videos.forSong') : t('videos.forAlbumShort') }} · {{ video.target.artist || t('common.unknownArtist') }}</span>
      </span>
    </RouterLink>
    <span v-else-if="video.file_path" class="truncate text-[13px] text-muted">{{ video.file_path }}</span>
    <VideoInfoSheet v-if="infoOpen" :video="video" @close="infoOpen = false" />
  </div>
</template>
