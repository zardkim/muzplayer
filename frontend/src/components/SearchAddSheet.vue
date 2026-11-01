<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Check, Plus, Search } from '@lucide/vue'
import { api, query } from '../api'
import { errorMessage } from '../i18n'
import { useLibrary } from '../stores/library'
import type { Page, Track, VideoListItem } from '../types'
import BaseModal from './BaseModal.vue'
import CoverArt from './CoverArt.vue'
import VideoThumb from './VideoThumb.vue'

// Adding to a playlist from a search: songs (a playlist) or music videos (a video playlist). Each
// result is added with its +; what is in the list already shows a check. The sheet stays open for more.
const props = defineProps<{ kind: 'tracks' | 'videos'; listId: number; listName: string; has: number[] }>()
const emit = defineEmits<{ close: []; added: [] }>()
const { t } = useI18n()
const library = useLibrary()
const q = ref('')
const tracks = ref<Track[]>([])
const videos = ref<VideoListItem[]>([])
const inList = ref(new Set(props.has))
const busy = ref(false)
const error = ref('')
let timer: number | undefined
let asked = 0
let changed = false

async function search() {
  const text = q.value.trim()
  const mine = ++asked
  busy.value = true
  error.value = ''
  try {
    if (props.kind === 'tracks') {
      const r = text ? await api<Page<Track>>(`/tracks${query({ q: text, limit: 40, sort: 'relevance' })}`) : { items: [] as Track[] }
      if (mine === asked) tracks.value = r.items
    } else {
      // videos: the newest ones before anything is typed (there are not many)
      const r = await api<Page<VideoListItem>>(`/videos${query({ q: text || undefined, limit: 60 })}`)
      if (mine === asked) videos.value = r.items
    }
  } catch (e) {
    error.value = errorMessage(e)
  } finally {
    if (mine === asked) busy.value = false
  }
}
watch(q, () => {
  clearTimeout(timer)
  timer = window.setTimeout(search, 250)
})
onMounted(() => {
  if (props.kind === 'videos') search()
  document.getElementById('add-q')?.focus()
})
onUnmounted(() => clearTimeout(timer))

async function add(id: number) {
  try {
    if (props.kind === 'tracks') {
      const track = tracks.value.find((x) => x.id === id)!
      await library.addToPlaylist(props.listId, [track])
    } else {
      await api(`/video-playlists/${props.listId}/videos`, { method: 'POST', body: { video_ids: [id] } })
    }
    inList.value = new Set(inList.value).add(id)
    changed = true
  } catch (e) {
    error.value = errorMessage(e)
  }
}
function close() {
  if (changed) emit('added')
  emit('close')
}
</script>

<template>
  <BaseModal wide :title="kind === 'tracks' ? t('playlists.addSongs', { name: listName }) : t('videos.addVideos', { name: listName })" @close="close">
    <div class="flex flex-col gap-3">
      <form class="flex h-11 items-center gap-2 rounded-full bg-surface px-4" role="search" @submit.prevent="search">
        <Search :size="18" :stroke-width="1.5" class="text-muted" aria-hidden="true" />
        <label for="add-q" class="sr-only">{{ t('search.label') }}</label>
        <input id="add-q" v-model="q" type="search" maxlength="200" :placeholder="kind === 'tracks' ? t('search.placeholder') : t('videos.searchVideos')" class="min-w-0 flex-1 bg-transparent text-[15px] outline-none" />
      </form>
      <p v-if="error" class="text-[14px] text-danger" role="alert">{{ error }}</p>
      <p v-else-if="kind === 'tracks' && !q.trim()" class="text-[14px] text-muted">{{ t('playlists.addHint') }}</p>
      <p v-else-if="!busy && (kind === 'tracks' ? !tracks.length : !videos.length)" class="text-[14px] text-muted">{{ t('search.noResults') }}</p>

      <ul v-if="kind === 'tracks'" class="flex flex-col" :class="busy ? 'opacity-60' : ''">
        <li v-for="tr in tracks" :key="tr.id" class="flex items-center gap-3 rounded-xl px-2 py-1.5 hover:bg-surface">
          <CoverArt :album-id="tr.album_id" :has-cover="tr.has_cover" :version="tr.cover_v" rounded="rounded-md" class="size-11 flex-none" />
          <span class="flex min-w-0 flex-1 flex-col">
            <span class="truncate text-[15px]">{{ tr.title }}</span>
            <span class="truncate text-[13px] text-muted">{{ tr.artist || t('common.unknownArtist') }} · {{ tr.album || t('common.unknownAlbum') }}</span>
          </span>
          <span v-if="inList.has(tr.id)" class="grid size-10 flex-none place-items-center text-accent" :aria-label="t('playlists.inList')"><Check :size="20" :stroke-width="2" /></span>
          <button v-else type="button" class="grid size-10 flex-none place-items-center rounded-full border border-line-strong hover:border-ink" :aria-label="`${t('common.add')}: ${tr.title}`" @click="add(tr.id)">
            <Plus :size="18" :stroke-width="1.8" />
          </button>
        </li>
      </ul>
      <ul v-else class="flex flex-col" :class="busy ? 'opacity-60' : ''">
        <li v-for="v in videos" :key="v.id" class="flex items-center gap-3 rounded-xl px-2 py-1.5 hover:bg-surface">
          <span class="relative aspect-video w-24 flex-none overflow-hidden rounded-lg bg-surface"><VideoThumb :video="v" :icon="18" /></span>
          <span class="flex min-w-0 flex-1 flex-col">
            <span class="line-clamp-2 text-[14px] leading-snug">{{ v.title }}</span>
            <span class="truncate text-[12px] text-muted">{{ t(`videos.kinds.${v.kind}`) }}<template v-if="v.target"> · {{ v.target.artist || v.target.title }}</template></span>
          </span>
          <span v-if="inList.has(v.id)" class="grid size-10 flex-none place-items-center text-accent" :aria-label="t('playlists.inList')"><Check :size="20" :stroke-width="2" /></span>
          <button v-else type="button" class="grid size-10 flex-none place-items-center rounded-full border border-line-strong hover:border-ink" :aria-label="`${t('common.add')}: ${v.title}`" @click="add(v.id)">
            <Plus :size="18" :stroke-width="1.8" />
          </button>
        </li>
      </ul>
    </div>
  </BaseModal>
</template>
