<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ArrowDownUp, ChevronRight, Clock, Download, FileUp, Heart, ListMusic, ListVideo, Plus, Settings, SquareCheckBig, Users, Zap } from '@lucide/vue'
import { api, coverUrl } from '../api'
import { errorMessage } from '../i18n'
import { canSave, offline } from '../offline'
import { useAuth } from '../stores/auth'
import { useLibrary } from '../stores/library'
import { usePlayer } from '../stores/player'
import { useUi } from '../stores/ui'
import type { Mix, Track, VideoPlaylist } from '../types'
import VideoRow from '../components/VideoRow.vue'
import { youtubeThumb } from '../youtube'
import BaseModal from '../components/BaseModal.vue'
import CoverArt from '../components/CoverArt.vue'
import MixCards from '../components/MixCards.vue'
import PageHeader from '../components/PageHeader.vue'
import PlaylistImportSheet from '../components/PlaylistImportSheet.vue'
import SelectPill from '../components/SelectPill.vue'
import SectionTitle from '../components/SectionTitle.vue'

const { t } = useI18n()
const auth = useAuth()
const library = useLibrary()
const player = usePlayer()
const ui = useUi()
const router = useRouter()

const favorites = ref<Track[]>([])
const mixes = ref<Mix[]>([])
const historyCount = ref(0)

onMounted(async () => {
  library.loadPlaylists().catch(() => {})
  library.loadVideoPlaylists().catch(() => {})
  api<{ items: Mix[] }>('/mixes').then((r) => (mixes.value = r.items), () => {})
  const [f, h] = await Promise.all([
    api<{ items: Track[] }>('/favorites').catch(() => ({ items: [] })),
    api<{ items: Track[] }>('/history?limit=1000').catch(() => ({ items: [] })),
  ])
  favorites.value = f.items
  historyCount.value = new Set(h.items.map((x) => x.id)).size
})

// (phones have no sidebar: the playlists are managed here, the full manager is /playlists)
// a playlist file from another player, being read (PlaylistImportSheet)
const importing = ref<File | null>(null)
const importInput = ref<HTMLInputElement | null>(null)
function pickImport(e: Event) {
  const input = e.target as HTMLInputElement
  importing.value = input.files?.[0] ?? null
  input.value = ''
}
// the order of my playlists (library store), as on the playlists page
const SORTS = ['recent', 'name', 'manual'] as const
const sort = computed({
  get: () => ((SORTS as readonly string[]).includes(ui.views.playlistSort) ? ui.views.playlistSort : 'recent'),
  set: (v: string) => (ui.views = { ...ui.views, playlistSort: v }),
})

// a new playlist of songs, or of videos
const creating = ref<'songs' | 'videos' | null>(null)
const newName = ref('')
async function create() {
  if (!newName.value.trim()) return
  try {
    if (creating.value === 'videos') {
      const p = await api<VideoPlaylist>('/video-playlists', { method: 'POST', body: { name: newName.value.trim() } })
      library.loadVideoPlaylists().catch(() => {})
      creating.value = null
      router.push({ name: 'video-playlist', params: { id: p.id } })
      return
    }
    const p = await library.createPlaylist(newName.value.trim())
    creating.value = null
    router.push({ name: 'playlist', params: { id: p.id } })
  } catch (e) {
    ui.notify(errorMessage(e), true)
  }
}
</script>

<template>
  <div class="flex flex-col gap-6">
    <PageHeader :title="t('library.title')" />

    <section class="flex flex-col gap-3">
      <div class="flex items-center justify-between">
        <RouterLink to="/playlists" class="text-[22px] font-bold">{{ t('nav.playlists') }}</RouterLink>
        <RouterLink to="/playlists" class="flex h-[34px] items-center gap-1.5 rounded-full border border-line-strong px-3.5 text-sm">
          <SquareCheckBig :size="15" :stroke-width="1.6" />{{ t('playlists.manage') }}
        </RouterLink>
      </div>
      <div class="-mr-5 flex items-center gap-2 overflow-x-auto pr-5 [scrollbar-width:none]">
        <button type="button" class="flex h-[38px] flex-none items-center gap-1 rounded-full bg-ink px-3.5 text-sm text-on-ink" @click="(newName = ''), (creating = 'songs')">
          <Plus :size="16" :stroke-width="1.8" />{{ t('playlists.toolNew') }}
        </button>
        <button type="button" class="flex h-[38px] flex-none items-center gap-1 rounded-full border border-line-strong px-3.5 text-sm" :title="t('importList.title')" @click="importInput?.click()">
          <FileUp :size="16" :stroke-width="1.6" />{{ t('importList.button') }}
        </button>
        <input ref="importInput" type="file" accept=".m3u,.m3u8,.pls,audio/x-mpegurl,audio/mpegurl,audio/x-scpls" class="hidden" @change="pickImport" />
        <SelectPill v-if="library.playlists.length > 1" v-model="sort" :label="t('common.sort')" :icon="ArrowDownUp" :options="SORTS.map((k) => ({ value: k, label: t(`playlists.sort_${k}`) }))" />
      </div>
      <p v-if="!library.playlists.length" class="font-light text-muted">{{ t('playlists.empty') }}</p>
      <RouterLink v-for="p in library.playlists" :key="p.id" :to="{ name: 'playlist', params: { id: p.id } }" class="flex items-center gap-3.5">
        <span class="grid size-[52px] flex-none place-items-center rounded-lg bg-surface"><Zap v-if="p.kind === 'smart'" :size="22" :stroke-width="1.3" /><ListMusic v-else :size="22" :stroke-width="1.3" /></span>
        <span class="flex flex-col">
          <span class="text-[17px]">{{ p.name }}</span>
          <span class="text-sm font-light text-muted">{{ p.kind === 'smart' ? t('smart.badge') : t('common.tracks', p.track_count ?? 0) }}</span>
        </span>
      </RouterLink>
    </section>

    <!-- everyone's shared playlists -->
    <section v-if="library.sharedPlaylists.length" class="flex flex-col gap-3">
      <h2 class="text-[22px] font-bold">{{ t('shared.title') }}</h2>
      <RouterLink v-for="p in library.sharedPlaylists" :key="p.id" :to="{ name: 'playlist', params: { id: p.id } }" class="flex items-center gap-3.5">
        <span class="grid size-[52px] flex-none place-items-center overflow-hidden rounded-lg bg-surface">
          <img v-if="p.cover" :src="coverUrl(p.cover.id, 'thumb', p.cover.v)" alt="" loading="lazy" class="h-full w-full object-cover" />
          <ListMusic v-else :size="22" :stroke-width="1.3" />
        </span>
        <span class="flex min-w-0 flex-col">
          <span class="truncate text-[17px]">{{ p.name }}</span>
          <span class="truncate text-sm font-light text-muted">{{ t('common.tracks', p.track_count ?? 0) }}{{ p.owner ? ` · ${p.owner}` : '' }}</span>
        </span>
      </RouterLink>
    </section>

    <!-- video playlists -->
    <section class="flex flex-col gap-3">
      <div class="flex items-center justify-between">
        <RouterLink :to="{ path: '/playlists', hash: '#video-playlists' }" class="text-[22px] font-bold">{{ t('videos.myVideoPlaylists') }}</RouterLink>
        <button type="button" class="flex h-[34px] items-center gap-1 rounded-full border border-line-strong px-3.5 text-sm" @click="(newName = ''), (creating = 'videos')">
          <Plus :size="16" :stroke-width="1.6" />{{ t('videos.newPlaylist') }}
        </button>
      </div>
      <p v-if="!library.videoPlaylists.length" class="font-light text-muted">{{ t('videos.noPlaylists') }}</p>
      <RouterLink v-for="p in library.videoPlaylists" :key="p.id" :to="{ name: 'video-playlist', params: { id: p.id } }" class="flex items-center gap-3.5">
        <span class="relative grid aspect-video w-[84px] flex-none place-items-center overflow-hidden rounded-lg bg-surface">
          <img v-if="p.thumb" :src="youtubeThumb(p.thumb)" alt="" loading="lazy" class="absolute inset-0 h-full w-full object-cover" />
          <ListVideo v-else :size="22" :stroke-width="1.3" />
        </span>
        <span class="flex flex-col">
          <span class="text-[17px]">{{ p.name }}</span>
          <span class="text-sm font-light text-muted">{{ t('videos.count', { n: p.count }) }}</span>
        </span>
      </RouterLink>
    </section>

    <button
      type="button"
      class="flex h-[84px] items-center justify-between rounded-2xl bg-bg px-5 text-left shadow-[0_4px_20px_rgba(17,17,19,0.08)] disabled:opacity-60"
      :disabled="!favorites.length"
      @click="player.playTracks(favorites, 0)"
    >
      <span class="text-lg font-medium">{{ t('library.playFavorites') }}</span>
      <span class="flex">
        <CoverArt
          v-for="(f, i) in favorites.slice(0, 3)"
          :key="f.id"
          :album-id="f.album_id"
          :has-cover="f.has_cover" :version="f.cover_v"
          rounded="rounded-full"
          class="size-10 border-2 border-bg"
          :class="i ? '-ml-3' : ''"
        />
      </span>
    </button>


    <!-- liked music videos: a row; the favorites page has them all -->
    <VideoRow liked :title="t('favorites.likedVideos')" :to="{ name: 'favorites', query: { tab: 'videos' } }" />

    <section v-if="mixes.length" class="flex flex-col gap-3">
      <SectionTitle :title="t('library.mixes')" />
      <MixCards :mixes="mixes" />
    </section>

    <nav class="flex flex-col">
      <RouterLink to="/favorites" class="flex h-[58px] items-center gap-4">
        <Heart :size="26" :stroke-width="1.2" /><span class="flex-1 text-lg font-light">{{ t('nav.favorites') }}</span>
        <span class="text-[15px] font-light text-muted">{{ t('library.tracksCount', { n: favorites.length }) }}</span><ChevronRight :size="18" class="text-subtle" />
      </RouterLink>
      <RouterLink to="/history" class="flex h-[58px] items-center gap-4">
        <Clock :size="26" :stroke-width="1.2" /><span class="flex-1 text-lg font-light">{{ t('nav.history') }}</span>
        <span class="text-[15px] font-light text-muted">{{ t('library.tracksCount', { n: historyCount }) }}</span><ChevronRight :size="18" class="text-subtle" />
      </RouterLink>
      <RouterLink v-if="canSave()" to="/downloads" class="flex h-[58px] items-center gap-4">
        <Download :size="26" :stroke-width="1.2" /><span class="flex-1 text-lg font-light">{{ t('offline.title') }}</span>
        <span class="text-[15px] font-light text-muted">{{ t('offline.listCount', { n: offline.lists.length }) }}</span><ChevronRight :size="18" class="text-subtle" />
      </RouterLink>
      <RouterLink to="/settings" class="flex h-[58px] items-center gap-4">
        <Settings :size="26" :stroke-width="1.2" /><span class="flex-1 text-lg font-light">{{ t('nav.settings') }}</span><ChevronRight :size="18" class="text-subtle" />
      </RouterLink>
      <RouterLink v-if="auth.user?.is_admin" to="/admin" class="flex h-[58px] items-center gap-4">
        <Users :size="26" :stroke-width="1.2" /><span class="flex-1 text-lg font-light">{{ t('nav.admin') }}</span><ChevronRight :size="18" class="text-subtle" />
      </RouterLink>
    </nav>


    <PlaylistImportSheet v-if="importing" :file="importing" @close="importing = null" />
    <BaseModal v-if="creating" :title="creating === 'videos' ? t('videos.newPlaylist') : t('playlists.new')" @close="creating = null">
      <form class="flex flex-col gap-4" @submit.prevent="create">
        <label class="flex flex-col gap-1.5 text-[13px] text-muted">
          {{ t('playlists.name') }}
          <input v-model="newName" maxlength="200" class="h-12 rounded-full bg-surface px-4 text-base text-ink outline-none focus:ring-2 focus:ring-ink" />
        </label>
        <button type="submit" class="h-12 rounded-full bg-ink text-on-ink disabled:opacity-40" :disabled="!newName.trim()">{{ t('common.create') }}</button>
      </form>
    </BaseModal>
  </div>
</template>
