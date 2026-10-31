<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ExternalLink, Play, Search, Trash2 } from '@lucide/vue'
import { api, query } from '../api'
import { appConfig } from '../config'
import { errorMessage } from '../i18n'
import { usePlayer } from '../stores/player'
import { useUi } from '../stores/ui'
import type { Video, VideoKind, VideoResult } from '../types'
import BaseModal from './BaseModal.vue'

// Videos of an album or a song (ui.videoTarget): watch them with YouTube's own player, add more
// from a YouTube search (or a pasted link). Videos never go into the music queue: YouTube's terms
// don't allow playing just their sound, and iPhones stop embedded videos when the screen locks.
const { t } = useI18n()
const ui = useUi()
const player = usePlayer()
const target = computed(() => ui.videoTarget!)
const KINDS: VideoKind[] = ['mv', 'live', 'cover', 'other']

const videos = ref<Video[]>([])
const current = ref<Video | null>(null)
const playError = ref<'embed' | 'gone' | null>(null)
const pausedMusic = ref(false)
const adding = ref(false)
const kind = ref<VideoKind>('mv')
const q = ref('')
const results = ref<VideoResult[] | null>(null)
const searching = ref(false)
const link = ref('')
const error = ref('')

const base = computed(() => (target.value.albumId ? `/albums/${target.value.albumId}` : `/tracks/${target.value.trackId}`))
const grouped = computed(() => KINDS.map((k) => ({ kind: k, items: videos.value.filter((v) => v.kind === k) })).filter((g) => g.items.length))
const youtubeSearchUrl = computed(() => `https://www.youtube.com/results?${new URLSearchParams({ search_query: q.value })}`)

function suggestion(k: VideoKind) {
  const { artist, title } = target.value
  return { mv: `${artist} ${title} MV`, live: `${artist} ${title} live`, cover: `${title} cover`, other: `${artist} ${title}` }[k].trim()
}

async function load() {
  videos.value = (await api<{ items: Video[] }>(`${base.value}/videos`)).items
}

onMounted(async () => {
  q.value = suggestion(kind.value)
  try {
    await load()
    if (!videos.value.length) adding.value = true
  } catch (e) {
    error.value = errorMessage(e)
  }
})

function setKind(k: VideoKind) {
  if (q.value === suggestion(kind.value)) q.value = suggestion(k) // keep what the user typed
  kind.value = k
}

// ---- YouTube's IFrame player ----
type YTPlayer = { loadVideoById(id: string): void; destroy(): void }
type YTNamespace = { Player: new (el: HTMLElement, opts: object) => YTPlayer; PlayerState: { PLAYING: number; ENDED: number } }
const host = ref<HTMLElement | null>(null)
let yt: YTPlayer | null = null

function youtubeApi(): Promise<YTNamespace> {
  const w = window as unknown as { YT?: YTNamespace & { loaded?: number }; onYouTubeIframeAPIReady?: () => void }
  if (w.YT?.Player) return Promise.resolve(w.YT)
  return new Promise((resolve) => {
    const prev = w.onYouTubeIframeAPIReady
    w.onYouTubeIframeAPIReady = () => {
      prev?.()
      resolve(w.YT!)
    }
    if (!document.querySelector('script[data-yt-api]')) {
      const s = document.createElement('script')
      s.src = 'https://www.youtube.com/iframe_api'
      s.dataset.ytApi = ''
      document.head.append(s)
    }
  })
}

async function watch(v: Video) {
  current.value = v
  playError.value = null
  await nextTick()
  if (yt) {
    yt.loadVideoById(v.youtube_id)
    return
  }
  const YT = await youtubeApi()
  if (!host.value || current.value?.id !== v.id) return
  // YouTube replaces the element it is given with its iframe: give it one Vue doesn't track
  const el = document.createElement('div')
  host.value.replaceChildren(el)
  yt = new YT.Player(el, {
    host: 'https://www.youtube-nocookie.com',
    videoId: v.youtube_id,
    width: '100%',
    height: '100%',
    playerVars: { autoplay: 1, playsinline: 1, rel: 0 },
    events: {
      onStateChange: (e: { data: number }) => {
        if (e.data === YT.PlayerState.PLAYING && player.playing) {
          player.toggle() // the song pauses while a video plays
          pausedMusic.value = true
        }
        if (e.data === YT.PlayerState.ENDED) next()
      },
      // 101/150: its owner allows YouTube only; 100: removed or private
      onError: (e: { data: number }) => (playError.value = e.data === 100 ? 'gone' : 'embed'),
    },
  })
}

function next() {
  const i = videos.value.findIndex((v) => v.id === current.value?.id)
  if (i >= 0 && i + 1 < videos.value.length) watch(videos.value[i + 1])
}

function resumeMusic() {
  if (!player.playing) player.toggle()
  pausedMusic.value = false
}

onUnmounted(() => yt?.destroy())

// ---- adding ----
async function search() {
  if (!q.value.trim()) return
  searching.value = true
  error.value = ''
  try {
    const params = query({ q: q.value.trim(), album_id: target.value.albumId, track_id: target.value.trackId })
    results.value = (await api<{ items: VideoResult[] }>(`/videos/search${params}`)).items
  } catch (e) {
    error.value = errorMessage(e)
  } finally {
    searching.value = false
  }
}

async function add(video: string, result?: VideoResult) {
  error.value = ''
  try {
    const body = { video, kind: kind.value, album_id: target.value.albumId ?? null, track_id: target.value.trackId ?? null }
    const v = await api<Video>('/videos', { method: 'POST', body })
    if (result) result.added = true
    link.value = ''
    ui.notify(t('videos.added'))
    await load()
    if (!current.value) watch(v)
  } catch (e) {
    error.value = errorMessage(e)
  }
}

async function remove(v: Video) {
  if (!confirm(t('videos.removeConfirm', { title: v.title }))) return
  try {
    await api(`/videos/${v.id}`, { method: 'DELETE' })
    if (current.value?.id === v.id) {
      yt?.destroy()
      yt = null
      current.value = null
    }
    await load()
  } catch (e) {
    ui.notify(errorMessage(e), true)
  }
}

const length = (sec: number | null) => (sec == null ? '' : `${Math.floor(sec / 60)}:${String(sec % 60).padStart(2, '0')}`)
const thumb = (id: string) => `https://i.ytimg.com/vi/${id}/mqdefault.jpg`
</script>

<template>
  <BaseModal :title="target.albumId ? t('videos.forAlbum') : t('videos.forTrack', { title: target.title })" @close="ui.videoTarget = null">
    <div class="flex flex-col gap-4">
      <!-- player -->
      <div v-if="current" class="flex flex-col gap-2">
        <div class="relative aspect-video overflow-hidden rounded-xl bg-black">
          <div ref="host" class="absolute inset-0" />
          <div v-if="playError" class="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-ink p-4 text-center text-[14px] text-on-ink">
            <p>{{ playError === 'gone' ? t('videos.unavailable') : t('videos.notEmbeddable') }}</p>
            <a :href="`https://www.youtube.com/watch?v=${current.youtube_id}`" target="_blank" rel="noopener" class="flex h-10 items-center gap-1.5 rounded-full bg-bg px-4 text-ink">
              <ExternalLink :size="16" />{{ t('videos.openYoutube') }}
            </a>
          </div>
        </div>
        <p class="truncate text-[15px] font-medium">{{ current.title }}</p>
        <button v-if="pausedMusic" type="button" class="self-start text-[14px] text-accent underline" @click="resumeMusic">{{ t('videos.resumeMusic') }}</button>
      </div>

      <!-- registered videos -->
      <p v-if="!videos.length && !adding" class="text-[15px] font-light text-muted">{{ t('videos.empty') }}</p>
      <section v-for="g in grouped" :key="g.kind" class="flex flex-col gap-1">
        <h3 class="text-[13px] font-medium text-muted">{{ t(`videos.kinds.${g.kind}`) }}</h3>
        <div v-for="v in g.items" :key="v.id" class="flex items-center gap-3 rounded-xl py-1.5" :class="current?.id === v.id ? 'bg-accent-soft' : ''">
          <button type="button" class="flex min-w-0 flex-1 items-center gap-3 text-left" :aria-label="`${t('common.play')}: ${v.title}`" @click="watch(v)">
            <span class="relative aspect-video w-28 flex-none overflow-hidden rounded-lg bg-surface">
              <img :src="thumb(v.youtube_id)" alt="" loading="lazy" class="h-full w-full object-cover" />
              <Play :size="18" class="absolute inset-0 m-auto text-white drop-shadow" fill="currentColor" />
            </span>
            <span class="flex min-w-0 flex-col">
              <span class="line-clamp-2 text-[14px] leading-snug">{{ v.title }}</span>
              <span class="truncate text-[12px] text-muted">{{ v.channel }}</span>
            </span>
          </button>
          <button v-if="v.can_edit" type="button" class="grid size-10 flex-none place-items-center text-muted" :aria-label="`${t('videos.remove')}: ${v.title}`" @click="remove(v)">
            <Trash2 :size="17" :stroke-width="1.4" />
          </button>
        </div>
      </section>

      <!-- add -->
      <button v-if="!adding" type="button" class="h-11 rounded-full border border-line-strong text-[15px]" @click="adding = true">{{ t('videos.add') }}</button>
      <section v-else class="flex flex-col gap-3 rounded-2xl bg-surface p-3.5">
        <div class="flex flex-wrap gap-1.5" role="radiogroup" :aria-label="t('videos.kind')">
          <button
            v-for="k in KINDS"
            :key="k"
            type="button"
            role="radio"
            :aria-checked="kind === k"
            class="h-9 rounded-full px-3.5 text-[14px]"
            :class="kind === k ? 'bg-ink text-on-ink' : 'bg-bg'"
            @click="setKind(k)"
          >
            {{ t(`videos.kinds.${k}`) }}
          </button>
        </div>

        <template v-if="appConfig.youtubeSearch">
          <form class="flex gap-2" role="search" @submit.prevent="search">
            <label for="video-q" class="sr-only">{{ t('videos.search') }}</label>
            <input id="video-q" v-model="q" maxlength="200" class="h-11 min-w-0 flex-1 rounded-full bg-bg px-4 text-[15px] outline-none focus:ring-2 focus:ring-ink" />
            <button type="submit" class="flex h-11 flex-none items-center gap-1.5 rounded-full bg-ink px-4 text-[15px] text-on-ink disabled:opacity-40" :disabled="searching || !q.trim()">
              <Search :size="16" />{{ t('videos.searchButton') }}
            </button>
          </form>
          <p v-if="searching" class="text-[14px] text-muted" role="status">{{ t('common.loading') }}</p>
          <ul v-if="results" class="flex flex-col gap-1">
            <li v-for="r in results" :key="r.youtube_id" class="flex items-center gap-3 py-1">
              <a :href="`https://www.youtube.com/watch?v=${r.youtube_id}`" target="_blank" rel="noopener" class="relative aspect-video w-28 flex-none overflow-hidden rounded-lg bg-bg">
                <img :src="thumb(r.youtube_id)" alt="" loading="lazy" class="h-full w-full object-cover" />
                <span v-if="r.duration" class="absolute bottom-1 right-1 rounded bg-black/75 px-1 text-[11px] text-white">{{ length(r.duration) }}</span>
              </a>
              <span class="flex min-w-0 flex-1 flex-col">
                <span class="line-clamp-2 text-[14px] leading-snug">{{ r.title }}</span>
                <span class="truncate text-[12px] text-muted">{{ r.channel }}</span>
              </span>
              <button
                type="button"
                class="h-9 flex-none rounded-full px-3.5 text-[14px] disabled:opacity-50"
                :class="r.added ? 'text-muted' : 'bg-ink text-on-ink'"
                :disabled="r.added"
                @click="add(r.youtube_id, r)"
              >
                {{ r.added ? t('videos.registered') : t('videos.register') }}
              </button>
            </li>
          </ul>
        </template>
        <template v-else>
          <p class="text-[13px] leading-relaxed text-muted">{{ t('videos.noKey') }}</p>
          <a :href="youtubeSearchUrl" target="_blank" rel="noopener" class="flex h-10 items-center gap-1.5 self-start rounded-full bg-bg px-4 text-[14px]">
            <ExternalLink :size="15" />{{ t('videos.searchOnYoutube') }}
          </a>
        </template>

        <!-- a link always works, also when a search can't find it -->
        <form class="flex gap-2" @submit.prevent="add(link)">
          <label for="video-link" class="sr-only">{{ t('videos.paste') }}</label>
          <input id="video-link" v-model="link" inputmode="url" maxlength="500" :placeholder="t('videos.pastePlaceholder')" class="h-11 min-w-0 flex-1 rounded-full bg-bg px-4 text-[15px] outline-none focus:ring-2 focus:ring-ink" />
          <button type="submit" class="h-11 flex-none rounded-full border border-line-strong bg-bg px-4 text-[15px] disabled:opacity-40" :disabled="link.trim().length < 11">{{ t('videos.register') }}</button>
        </form>
        <p v-if="error" class="text-[14px] text-danger" role="alert">{{ error }}</p>
      </section>
    </div>
  </BaseModal>
</template>
