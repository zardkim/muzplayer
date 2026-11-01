<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { EllipsisVertical, Play } from '@lucide/vue'
import { api } from '../api'
import { errorMessage } from '../i18n'
import { useUi } from '../stores/ui'
import { VIDEO_KINDS, type VideoKind, type VideoListItem } from '../types'
import CoverArt from './CoverArt.vue'
import VideoThumb from './VideoThumb.vue'
import YoutubeIcon from './YoutubeIcon.vue'

// One music video in a grid: its picture plays it; the menu puts it in a video playlist and lets
// who added it (or an admin) change its kind or remove it; a NAS file also its title, and its
// thumbnail made again from another scene.
const props = defineProps<{ video: VideoListItem }>()
const emit = defineEmits<{ play: []; changed: [] }>()
const { t } = useI18n()
const ui = useUi()
const menu = ref(false)
const menuUp = ref(false) // cards low on the screen open their menu upwards
function toggleMenu(e: MouseEvent) {
  menuUp.value = (e.currentTarget as HTMLElement).getBoundingClientRect().top > window.innerHeight / 2
  menu.value = !menu.value
}

async function setKind(kind: VideoKind) {
  menu.value = false
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
// a NAS file's song: found from its name, or let go
async function link(auto: boolean) {
  menu.value = false
  try {
    const v = await api<VideoListItem>(`/videos/${props.video.id}/link`, { method: 'POST', body: { auto } })
    ui.notify(v.target ? t('videos.linkedTo', { song: `${v.target.title} · ${v.target.artist}` }) : t('videos.unlinked'))
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
}
onMounted(() => document.addEventListener('click', outside))
onUnmounted(() => document.removeEventListener('click', outside))
</script>

<template>
  <div class="flex flex-col gap-2.5">
    <button type="button" class="group relative aspect-video overflow-hidden rounded-xl bg-surface" :aria-label="`${t('videos.play')}: ${video.title}`" @click="emit('play')">
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
        <div v-if="menu" class="absolute right-0 z-30 flex w-52 flex-col overflow-hidden rounded-2xl border border-line bg-bg py-1.5 text-[14px] shadow-xl" :class="menuUp ? 'bottom-9' : 'top-9'">
          <button type="button" class="px-4 py-2.5 text-left hover:bg-surface" @click="(menu = false), (ui.videoPick = [video])">{{ t('videos.addToPlaylist') }}</button>
          <template v-if="video.can_edit">
            <div class="my-1 border-t border-line" />
            <!-- NAS files: their title and thumbnail are ours to change -->
            <template v-if="video.file_path">
              <button type="button" class="px-4 py-2.5 text-left hover:bg-surface" @click="rename">{{ t('videos.renameVideo') }}</button>
              <button type="button" class="px-4 py-2.5 text-left hover:bg-surface" :disabled="remaking" @click="remakeThumb">{{ t('videos.remakeThumb') }}</button>
              <button v-if="video.track_id" type="button" class="px-4 py-2.5 text-left hover:bg-surface" @click="link(false)">{{ t('videos.unlink') }}</button>
              <button v-else type="button" class="px-4 py-2.5 text-left hover:bg-surface" @click="link(true)">{{ t('videos.autoLink') }}</button>
              <div class="my-1 border-t border-line" />
            </template>
            <p class="px-4 pb-1 pt-1.5 text-[12px] text-muted">{{ t('videos.changeKind') }}</p>
            <button
              v-for="k in VIDEO_KINDS"
              :key="k"
              type="button"
              class="px-4 py-2 text-left hover:bg-surface"
              :class="video.kind === k ? 'font-medium text-accent' : ''"
              :disabled="video.kind === k"
              @click="setKind(k)"
            >{{ t(`videos.kinds.${k}`) }}</button>
            <div class="my-1 border-t border-line" />
            <button type="button" class="px-4 py-2.5 text-left text-danger hover:bg-surface" @click="remove">{{ t('videos.remove') }}</button>
          </template>
        </div>
      </span>
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
  </div>
</template>
