<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { ExternalLink, ListPlus, Repeat, Shuffle } from '@lucide/vue'
import { api } from '../api'
import { usePlayer } from '../stores/player'
import { useUi } from '../stores/ui'
import type { VideoListItem } from '../types'
import { youtubeApi, type YTPlayer } from '../youtube'
import BaseModal from './BaseModal.vue'
import PlayerIcons from './PlayerIcons.vue'
import ArtistPhoto from './ArtistPhoto.vue'
import VideoThumb from './VideoThumb.vue'

// The video player (ui.videoQueue): videos played large, one after another or shuffled, YouTube
// ones with YouTube's player, NAS files with the browser's. From the Music videos page, a search,
// or a video playlist. The music pauses while a video plays. Under it: what plays next, similar
// music videos (one picked plays now) and similar artists (their pages).
const { t } = useI18n()
const ui = useUi()
const player = usePlayer()
const queue = ui.videoQueue!
const items = [...queue.items] // a similar video picked joins it

const shuffle = ref(!!queue.shuffle)
const repeat = ref(false)
const order = ref<number[]>([])
const pos = ref(0)
const current = computed<VideoListItem | undefined>(() => items[order.value[pos.value]])
const playError = ref<'embed' | 'gone' | null>(null)
const pausedMusic = ref(false)

/** The play order: in list order, or shuffled; `first` (an index into items) plays first. */
function arrange(first: number) {
  const rest = items.map((_, i) => i).filter((i) => i !== first)
  if (shuffle.value) {
    for (let i = rest.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1))
      ;[rest[i], rest[j]] = [rest[j], rest[i]]
    }
    order.value = [first, ...rest]
  } else order.value = items.map((_, i) => i).slice(first).concat(items.map((_, i) => i).slice(0, first))
  pos.value = 0
}

function toggleShuffle() {
  shuffle.value = !shuffle.value
  arrange(order.value[pos.value])
}

function next() {
  const before = current.value
  if (pos.value + 1 < order.value.length) pos.value++
  else if (repeat.value) {
    if (shuffle.value) arrange(order.value[Math.floor(Math.random() * order.value.length)])
    else pos.value = 0
  }
  if (repeat.value && current.value === before) replay() // the only video, again
}
const fileEl = ref<HTMLVideoElement | null>(null)
function replay() {
  if (fileEl.value) {
    fileEl.value.currentTime = 0
    fileEl.value.play().catch(() => {})
  } else if (current.value?.youtube_id) yt?.loadVideoById(current.value.youtube_id)
}
function prev() {
  if (pos.value > 0) pos.value--
}

// ---- YouTube's IFrame player (made once, given each YouTube video in turn) ----
const host = ref<HTMLElement | null>(null)
let yt: YTPlayer | null = null

function pauseMusic() {
  if (player.playing) {
    player.toggle()
    pausedMusic.value = true
  }
}

async function show(v: VideoListItem | undefined) {
  playError.value = null
  if (!v) return
  if (!v.youtube_id) {
    yt?.destroy()
    yt = null
    return // the <video> element plays it
  }
  await nextTick()
  if (yt) {
    yt.loadVideoById(v.youtube_id)
    return
  }
  const YT = await youtubeApi()
  if (!host.value || current.value?.id !== v.id) return
  const el = document.createElement('div') // YouTube replaces it with its iframe: one Vue doesn't track
  host.value.replaceChildren(el)
  yt = new YT.Player(el, {
    host: 'https://www.youtube-nocookie.com',
    videoId: v.youtube_id,
    width: '100%',
    height: '100%',
    playerVars: { autoplay: 1, playsinline: 1, rel: 0 },
    events: {
      onStateChange: (e: { data: number }) => {
        if (e.data === YT.PlayerState.PLAYING) pauseMusic()
        if (e.data === YT.PlayerState.ENDED) next()
      },
      // 101/150: its owner allows YouTube only; 100: removed or private
      onError: (e: { data: number }) => (playError.value = e.data === 100 ? 'gone' : 'embed'),
    },
  })
}

watch(current, (v) => show(v))

// ---- similar music videos and artists (of the one playing) ----
type Related = { videos: VideoListItem[]; artists: { id: number; name: string; image_v: number }[] }
const related = ref<Related | null>(null)
watch(
  () => current.value?.id,
  async (id) => {
    if (!id) return
    try {
      const r = await api<Related>(`/videos/${id}/related`)
      if (current.value?.id === id) related.value = r
    } catch {
      related.value = null
    }
  },
  { immediate: true },
)
const upNext = computed(() => (pos.value + 1 < order.value.length ? items[order.value[pos.value + 1]] : null))
/** A similar video: played now, the rest of the list after it. */
function playRelated(v: VideoListItem) {
  let i = items.findIndex((x) => x.id === v.id)
  if (i < 0) i = items.push(v) - 1
  const at = order.value.indexOf(i)
  if (at >= 0) order.value.splice(at, 1)
  const here = order.value.indexOf(order.value[pos.value])
  order.value.splice(here + 1, 0, i)
  pos.value = here + 1
}
onMounted(() => {
  arrange(Math.min(Math.max(queue.start, 0), items.length - 1))
  show(current.value)
})
onUnmounted(() => yt?.destroy())

function close() {
  ui.videoQueue = null
}
</script>

<template>
  <BaseModal video :title="queue.title || current?.title || t('videos.pageTitle')" @close="close">
    <div v-if="current" class="flex flex-col gap-4">
      <div class="relative mx-auto aspect-video w-full overflow-hidden rounded-xl bg-black" style="max-width: calc((94vh - 250px) * 16 / 9)">
        <video
          v-if="!current.youtube_id"
          ref="fileEl"
          :key="current.id"
          :src="`/api/v1/videos/${current.id}/file`"
          controls
          autoplay
          playsinline
          class="absolute inset-0 h-full w-full"
          @play="pauseMusic"
          @ended="next"
          @error="playError = 'embed'"
        />
        <div v-else ref="host" class="absolute inset-0" />
        <div v-if="playError" class="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-ink p-4 text-center text-[14px] text-on-ink">
          <p>{{ !current.youtube_id ? t('videos.fileCantPlay') : playError === 'gone' ? t('videos.unavailable') : t('videos.notEmbeddable') }}</p>
          <a v-if="current.youtube_id" :href="`https://www.youtube.com/watch?v=${current.youtube_id}`" target="_blank" rel="noopener" class="flex h-10 items-center gap-1.5 rounded-full bg-bg px-4 text-ink">
            <ExternalLink :size="16" />{{ t('videos.openYoutube') }}
          </a>
          <button v-if="order.length > 1" type="button" class="text-[14px] underline" @click="next">{{ t('videos.skip') }}</button>
        </div>
      </div>

      <div class="flex flex-wrap items-center gap-x-4 gap-y-2">
        <div class="flex min-w-0 flex-1 flex-col">
          <span class="truncate text-[17px] font-medium">{{ current.title }}</span>
          <span class="truncate text-[13px] text-muted">
            {{ t(`videos.kinds.${current.kind}`) }}
            <template v-if="current.target"> · {{ current.target.title }} · {{ current.target.artist || t('common.unknownArtist') }}</template>
            <template v-else-if="current.file_path"> · {{ t('videos.nas') }}</template>
          </span>
        </div>
        <div class="flex items-center gap-1">
          <button type="button" class="grid size-10 place-items-center rounded-full" :class="shuffle ? 'bg-ink text-on-ink' : 'hover:bg-surface'" :aria-pressed="shuffle" :aria-label="t('videos.shuffle')" :title="t('videos.shuffle')" @click="toggleShuffle">
            <Shuffle :size="18" :stroke-width="1.6" />
          </button>
          <button type="button" class="grid size-11 place-items-center disabled:opacity-30" :disabled="pos === 0" :aria-label="t('videos.prevVideo')" :title="t('videos.prevVideo')" @click="prev">
            <PlayerIcons name="prev" :size="24" :stroke="1.3" />
          </button>
          <button type="button" class="grid size-11 place-items-center disabled:opacity-30" :disabled="pos + 1 >= order.length && !repeat" :aria-label="t('videos.nextVideo')" :title="t('videos.nextVideo')" @click="next">
            <PlayerIcons name="next" :size="24" :stroke="1.3" />
          </button>
          <button type="button" class="grid size-10 place-items-center rounded-full" :class="repeat ? 'bg-ink text-on-ink' : 'hover:bg-surface'" :aria-pressed="repeat" :aria-label="t('videos.repeat')" :title="t('videos.repeat')" @click="repeat = !repeat">
            <Repeat :size="18" :stroke-width="1.6" />
          </button>
          <button type="button" class="grid size-10 place-items-center rounded-full hover:bg-surface" :aria-label="t('videos.addToPlaylist')" :title="t('videos.addToPlaylist')" @click="ui.videoPick = [current]">
            <ListPlus :size="19" :stroke-width="1.6" />
          </button>
        </div>
      </div>
      <button v-if="pausedMusic" type="button" class="-mt-2 self-start text-[14px] text-accent underline" @click="player.toggle(), (pausedMusic = false)">{{ t('videos.resumeMusic') }}</button>

      <!-- what plays next (the whole order stays behind the arrows and shuffle) -->
      <button v-if="upNext" type="button" class="-mt-1 flex min-w-0 items-center gap-2 self-start text-[13px] text-muted hover:text-ink" @click="next">
        <span class="flex-none">{{ t('videos.nextUp') }}</span><span class="truncate text-ink">{{ upNext.title }}</span>
      </button>

      <!-- similar music videos -->
      <section v-if="related?.videos.length" class="flex flex-col gap-2">
        <h3 class="text-[15px] font-bold">{{ t('videos.similarVideos') }}</h3>
        <ul class="grid grid-cols-2 gap-x-3 gap-y-4 sm:grid-cols-3 lg:grid-cols-4">
          <li v-for="v in related.videos" :key="v.id">
            <button type="button" class="group flex w-full flex-col gap-1.5 text-left" :aria-label="`${t('videos.play')}: ${v.title}`" @click="playRelated(v)">
              <span class="relative block aspect-video w-full overflow-hidden rounded-lg bg-surface">
                <VideoThumb :video="v" :icon="20" />
              </span>
              <span class="line-clamp-2 text-[13px] leading-snug">{{ v.title }}</span>
              <span v-if="v.target" class="truncate text-[12px] text-muted">{{ v.target.artist || v.target.title }}</span>
            </button>
          </li>
        </ul>
      </section>

      <!-- similar artists: their pages -->
      <section v-if="related?.artists.length" class="flex flex-col gap-2">
        <h3 class="text-[15px] font-bold">{{ t('videos.similarArtists') }}</h3>
        <div class="-mx-1 flex gap-3 overflow-x-auto px-1 pb-1 [scrollbar-width:none]">
          <RouterLink v-for="a in related.artists" :key="a.id" :to="{ name: 'artist', params: { id: a.id } }" class="flex w-20 flex-none flex-col items-center gap-1.5 text-center">
            <ArtistPhoto :artist-id="a.id" :name="a.name" :version="a.image_v" class="size-20" />
            <span class="line-clamp-2 text-[12px] leading-tight">{{ a.name }}</span>
          </RouterLink>
        </div>
      </section>
    </div>
  </BaseModal>
</template>
