<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ArrowDown, ArrowUp, Film, Pencil, Play, Shuffle, Trash2, X } from '@lucide/vue'
import { api } from '../api'
import { errorMessage } from '../i18n'
import { useUi } from '../stores/ui'
import type { VideoPlaylist } from '../types'
import { youtubeThumb } from '../youtube'
import PageHeader from '../components/PageHeader.vue'

// One video playlist: play it in order or shuffled (the video player), a video from where it is;
// rename, reorder, remove videos, delete the list.
const props = defineProps<{ id: string }>()
const { t } = useI18n()
const router = useRouter()
const ui = useUi()
const playlist = ref<VideoPlaylist | null>(null)
const error = ref('')
const entries = computed(() => playlist.value?.entries ?? [])
const videos = computed(() => entries.value.map((e) => e.video))

async function load() {
  try {
    playlist.value = await api<VideoPlaylist>(`/video-playlists/${props.id}`)
  } catch (e) {
    error.value = errorMessage(e)
  }
}
onMounted(load)

function play(start: number, shuffle = false) {
  if (!videos.value.length) return
  ui.videoQueue = { items: videos.value, start, shuffle, title: playlist.value!.name }
}

async function act(fn: () => Promise<unknown>) {
  try {
    await fn()
    await load()
  } catch (e) {
    ui.notify(errorMessage(e), true)
  }
}
function rename() {
  const name = prompt(t('videos.renamePlaylist'), playlist.value!.name)?.trim()
  if (name) act(() => api(`/video-playlists/${props.id}`, { method: 'PATCH', body: { name } }))
}
function remove(entryId: number) {
  act(() => api(`/video-playlists/${props.id}/videos/${entryId}`, { method: 'DELETE' }))
}
function move(i: number, dir: -1 | 1) {
  const ids = entries.value.map((e) => e.entry_id)
  ;[ids[i], ids[i + dir]] = [ids[i + dir], ids[i]]
  act(() => api(`/video-playlists/${props.id}/order`, { method: 'PUT', body: { entry_ids: ids } }))
}
async function destroy() {
  if (!confirm(t('playlists.deleteConfirm', { name: playlist.value!.name }))) return
  try {
    await api(`/video-playlists/${props.id}`, { method: 'DELETE' })
    router.replace({ name: 'playlists' })
  } catch (e) {
    ui.notify(errorMessage(e), true)
  }
}
</script>

<template>
  <div class="flex flex-col gap-6">
    <p v-if="error" class="font-light text-muted">{{ error }}</p>
    <template v-if="playlist">
      <PageHeader :title="playlist.name" :sub="`${t('videos.videoPlaylist')} · ${t('videos.count', { n: playlist.count })}`" />
      <div class="-mt-2 flex flex-wrap gap-2">
        <button type="button" class="flex h-11 items-center gap-1.5 rounded-full bg-ink px-5 text-[15px] text-on-ink disabled:opacity-40" :disabled="!videos.length" @click="play(0)">
          <Play :size="16" fill="currentColor" />{{ t('videos.playAll') }}
        </button>
        <button type="button" class="flex h-11 items-center gap-1.5 rounded-full border border-line-strong px-5 text-[15px] disabled:opacity-40" :disabled="!videos.length" @click="play(Math.floor(Math.random() * videos.length), true)">
          <Shuffle :size="17" :stroke-width="1.6" />{{ t('videos.shufflePlay') }}
        </button>
        <button type="button" class="grid size-11 place-items-center rounded-full border border-line-strong" :aria-label="t('videos.renamePlaylist')" :title="t('videos.renamePlaylist')" @click="rename">
          <Pencil :size="17" :stroke-width="1.5" />
        </button>
        <button type="button" class="grid size-11 place-items-center rounded-full border border-line-strong text-danger" :aria-label="t('videos.deletePlaylist')" :title="t('videos.deletePlaylist')" @click="destroy">
          <Trash2 :size="17" :stroke-width="1.5" />
        </button>
      </div>

      <p v-if="!entries.length" class="max-w-xl font-light leading-relaxed text-muted">{{ t('videos.playlistEmpty') }}</p>
      <ol class="flex flex-col">
        <li v-for="(e, i) in entries" :key="e.entry_id" class="flex items-center gap-3 border-b border-surface py-2">
          <span class="w-6 flex-none text-center font-display text-[14px] text-muted">{{ i + 1 }}</span>
          <button type="button" class="flex min-w-0 flex-1 items-center gap-3.5 text-left" :aria-label="`${t('videos.play')}: ${e.video.title}`" @click="play(i)">
            <span class="relative aspect-video w-32 flex-none overflow-hidden rounded-lg bg-surface sm:w-40">
              <img v-if="e.video.youtube_id" :src="youtubeThumb(e.video.youtube_id)" alt="" loading="lazy" class="h-full w-full object-cover" />
              <Film v-else :size="22" :stroke-width="1.3" class="absolute inset-0 m-auto text-muted" />
            </span>
            <span class="flex min-w-0 flex-col gap-0.5">
              <span class="line-clamp-2 text-[15px] leading-snug">{{ e.video.title }}</span>
              <span class="truncate text-[13px] text-muted">
                {{ t(`videos.kinds.${e.video.kind}`) }}<template v-if="e.video.target"> · {{ e.video.target.title }}</template><template v-else-if="e.video.file_path"> · {{ t('videos.nas') }}</template>
              </span>
            </span>
          </button>
          <span class="flex flex-none items-center">
            <button type="button" class="hidden size-9 place-items-center text-muted hover:text-ink disabled:opacity-30 sm:grid" :disabled="i === 0" :aria-label="t('common.moveUp')" @click="move(i, -1)"><ArrowUp :size="17" /></button>
            <button type="button" class="hidden size-9 place-items-center text-muted hover:text-ink disabled:opacity-30 sm:grid" :disabled="i === entries.length - 1" :aria-label="t('common.moveDown')" @click="move(i, 1)"><ArrowDown :size="17" /></button>
            <button type="button" class="grid size-10 place-items-center text-muted hover:text-danger" :aria-label="`${t('common.remove')}: ${e.video.title}`" @click="remove(e.entry_id)"><X :size="18" /></button>
          </span>
        </li>
      </ol>
    </template>
  </div>
</template>
