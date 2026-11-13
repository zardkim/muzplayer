<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ChevronRight, ListMusic, ListVideo, Plus, Sparkles, Zap } from '@lucide/vue'
import { api } from '../api'
import { appConfig } from '../config'
import { errorMessage } from '../i18n'
import { useLibrary } from '../stores/library'
import { useUi } from '../stores/ui'
import PageHeader from '../components/PageHeader.vue'
import AiPlaylistSheet, { type AiDraft } from '../components/AiPlaylistSheet.vue'
import SmartRulesSheet from '../components/SmartRulesSheet.vue'
import BookGrid from '../components/BookGrid.vue'
import type { Book, Playlist, VideoPlaylist } from '../types'
import { youtubeThumb } from '../youtube'

const { t } = useI18n()
const library = useLibrary()
const ui = useUi()
const router = useRouter()
const route = useRoute()
const name = ref('')
const smartOpen = ref(false)
const aiOpen = ref(false)
const draft = ref<AiDraft | undefined>()
function drafted(d: AiDraft) {
  aiOpen.value = false
  draft.value = d
  smartOpen.value = true
}

function smartSaved(p: Playlist) {
  smartOpen.value = false
  library.loadPlaylists().catch(() => {})
  router.push({ name: 'playlist', params: { id: p.id } })
}
// My playlists by what they hold: music, music videos, audiobooks (the books being listened to and
// the finished ones); the tab is in the address (?tab=video), so back comes to it
type Tab = 'music' | 'video' | 'books'
const tabs = computed<Tab[]>(() => (appConfig.audiobooks ? ['music', 'video', 'books'] : ['music', 'video']))
const tab = computed<Tab>({
  get: () => {
    // (My Music's "my video playlists" link: #video-playlists)
    const want = route.hash === '#video-playlists' ? 'video' : route.query.tab
    return tabs.value.includes(want as Tab) ? (want as Tab) : 'music'
  },
  set: (v) => void router.replace({ query: v === 'music' ? {} : { tab: v }, hash: '' }),
})
// video playlists (music videos played one after another or shuffled)
const videoName = ref('')
onMounted(() => {
  library.loadPlaylists().catch(() => {})
  library.loadVideoPlaylists().catch(() => {})
})
// my audiobooks, asked for when their tab opens
const books = ref<{ listening: Book[]; finished: Book[] } | null>(null)
watch(tab, (v) => {
  if (v === 'books' && !books.value) api<{ listening: Book[]; finished: Book[] }>('/books/mine').then((r) => (books.value = r), () => (books.value = { listening: [], finished: [] }))
}, { immediate: true })
async function createVideoList() {
  if (!videoName.value.trim()) return
  try {
    const p = await api<VideoPlaylist>('/video-playlists', { method: 'POST', body: { name: videoName.value.trim() } })
    library.loadVideoPlaylists().catch(() => {})
    router.push({ name: 'video-playlist', params: { id: p.id } })
  } catch (e) {
    ui.notify(errorMessage(e), true)
  }
}

async function create() {
  if (!name.value.trim()) return
  try {
    const p = await library.createPlaylist(name.value.trim())
    router.push({ name: 'playlist', params: { id: p.id } })
  } catch (e) {
    ui.notify(errorMessage(e), true)
  }
}
</script>

<template>
  <div class="flex flex-col gap-6">
    <PageHeader :title="t('playlists.title')" />
    <div class="-mt-2 flex self-start rounded-full bg-surface p-1" role="tablist" :aria-label="t('playlists.title')">
      <button
        v-for="k in tabs"
        :key="k"
        type="button"
        role="tab"
        :aria-selected="tab === k"
        class="flex h-9 items-center gap-1.5 whitespace-nowrap rounded-full px-3.5 text-[14px] font-medium"
        :class="tab === k ? 'bg-bg text-ink shadow-sm' : 'text-muted'"
        @click="tab = k"
      >{{ t(`playlists.tab_${k}`) }}<span class="tabular-nums text-[12px] opacity-70">{{ k === 'music' ? library.playlists.length : k === 'video' ? library.videoPlaylists.length : books ? books.listening.length + books.finished.length : '' }}</span></button>
    </div>

    <template v-if="tab === 'music'">
    <form class="flex max-w-md gap-2" @submit.prevent="create">
      <label for="pl-name" class="sr-only">{{ t('playlists.name') }}</label>
      <input id="pl-name" v-model="name" maxlength="200" :placeholder="t('playlists.new')" class="h-11 min-w-0 flex-1 rounded-full bg-surface px-4 text-base outline-none focus:ring-2 focus:ring-ink" />
      <button type="submit" class="flex h-11 items-center gap-1 rounded-full bg-ink px-4 text-[15px] text-on-ink disabled:opacity-40" :disabled="!name.trim()">
        <Plus :size="18" :stroke-width="1.6" />{{ t('common.create') }}
      </button>
    </form>
    <div class="flex flex-wrap gap-2">
      <button type="button" class="flex h-11 items-center gap-1.5 rounded-full border border-line-strong px-4 text-[15px]" @click="(draft = undefined), (smartOpen = true)">
        <Zap :size="17" :stroke-width="1.5" />{{ t('smart.new') }}
      </button>
      <button v-if="appConfig.aiPlaylists" type="button" class="flex h-11 items-center gap-1.5 rounded-full border border-line-strong px-4 text-[15px]" @click="aiOpen = true">
        <Sparkles :size="17" :stroke-width="1.5" />{{ t('ai.title') }}
      </button>
    </div>
    <AiPlaylistSheet v-if="aiOpen" @close="aiOpen = false" @draft="drafted" />
    <SmartRulesSheet v-if="smartOpen" :draft="draft" @close="smartOpen = false" @saved="smartSaved" />
    <p v-if="!library.playlists.length" class="font-light text-muted">{{ t('playlists.empty') }}</p>
    <ul class="grid grid-cols-1 gap-x-8 sm:grid-cols-2 xl:grid-cols-3">
      <li v-for="p in library.playlists" :key="p.id">
        <RouterLink :to="{ name: 'playlist', params: { id: p.id } }" class="flex min-h-[72px] items-center gap-3.5 border-b border-surface">
          <span class="grid size-[52px] flex-none place-items-center rounded-lg bg-surface"><Zap v-if="p.kind === 'smart'" :size="22" :stroke-width="1.3" /><ListMusic v-else :size="22" :stroke-width="1.3" /></span>
          <span class="flex min-w-0 flex-1 flex-col">
            <span class="truncate text-[17px]">{{ p.name }}</span>
            <span class="text-sm font-light text-muted">{{ p.kind === 'smart' ? t('smart.badge') : t('common.tracks', p.track_count ?? 0) }}</span>
          </span>
          <ChevronRight :size="18" class="text-subtle" />
        </RouterLink>
      </li>
    </ul>

    </template>

    <!-- video playlists -->
    <section v-if="tab === 'video'" id="video-playlists" class="flex flex-col gap-4">
      <form class="flex max-w-md gap-2" @submit.prevent="createVideoList">
        <label for="vpl-name" class="sr-only">{{ t('videos.newPlaylist') }}</label>
        <input id="vpl-name" v-model="videoName" maxlength="200" :placeholder="t('videos.newPlaylist')" class="h-11 min-w-0 flex-1 rounded-full bg-surface px-4 text-base outline-none focus:ring-2 focus:ring-ink" />
        <button type="submit" class="flex h-11 items-center gap-1 rounded-full bg-ink px-4 text-[15px] text-on-ink disabled:opacity-40" :disabled="!videoName.trim()">
          <Plus :size="18" :stroke-width="1.6" />{{ t('common.create') }}
        </button>
      </form>
      <p v-if="!library.videoPlaylists.length" class="font-light text-muted">{{ t('videos.noPlaylists') }}</p>
      <ul class="grid grid-cols-1 gap-x-8 sm:grid-cols-2 xl:grid-cols-3">
        <li v-for="p in library.videoPlaylists" :key="p.id">
          <RouterLink :to="{ name: 'video-playlist', params: { id: p.id } }" class="flex min-h-[72px] items-center gap-3.5 border-b border-surface">
            <span class="relative grid aspect-video w-[84px] flex-none place-items-center overflow-hidden rounded-lg bg-surface">
              <img v-if="p.thumb" :src="youtubeThumb(p.thumb)" alt="" loading="lazy" class="absolute inset-0 h-full w-full object-cover" />
              <ListVideo v-else :size="22" :stroke-width="1.3" />
            </span>
            <span class="flex min-w-0 flex-1 flex-col">
              <span class="truncate text-[17px]">{{ p.name }}</span>
              <span class="text-sm font-light text-muted">{{ t('videos.count', { n: p.count }) }}</span>
            </span>
            <ChevronRight :size="18" class="text-subtle" />
          </RouterLink>
        </li>
      </ul>
    </section>

    <!-- my audiobooks: being listened to, finished -->
    <template v-if="tab === 'books'">
      <p v-if="!books" class="font-light text-muted">{{ t('common.loading') }}</p>
      <p v-else-if="!books.listening.length && !books.finished.length" class="font-light text-muted">{{ t('playlists.booksEmpty') }}</p>
      <template v-else>
        <section v-if="books.listening.length" class="flex flex-col gap-3.5">
          <h2 class="text-[20px] font-bold">{{ t('playlists.booksListening') }} <span class="text-[15px] font-normal text-muted">{{ books.listening.length }}</span></h2>
          <BookGrid :books="books.listening" />
        </section>
        <section v-if="books.finished.length" class="flex flex-col gap-3.5">
          <h2 class="text-[20px] font-bold">{{ t('playlists.booksFinished') }} <span class="text-[15px] font-normal text-muted">{{ books.finished.length }}</span></h2>
          <BookGrid :books="books.finished" />
        </section>
      </template>
    </template>
  </div>
</template>
