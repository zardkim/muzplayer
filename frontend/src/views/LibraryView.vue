<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ChevronRight, Clock, Download, Heart, ListMusic, ListVideo, Plus, Settings, Users, Zap } from '@lucide/vue'
import { api } from '../api'
import { errorMessage } from '../i18n'
import { canSave, offline } from '../offline'
import { useAuth } from '../stores/auth'
import { useLibrary } from '../stores/library'
import { usePlayer } from '../stores/player'
import { useUi } from '../stores/ui'
import type { Mix, Track, VideoListItem, VideoPlaylist } from '../types'
import VideoThumb from '../components/VideoThumb.vue'
import { youtubeThumb } from '../youtube'
import BaseModal from '../components/BaseModal.vue'
import CoverArt from '../components/CoverArt.vue'
import MixCards from '../components/MixCards.vue'
import PageHeader from '../components/PageHeader.vue'
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
const likedVideos = ref<VideoListItem[]>([])
const likedVideoCount = ref(0)

onMounted(async () => {
  library.loadPlaylists().catch(() => {})
  library.loadVideoPlaylists().catch(() => {})
  api<{ items: VideoListItem[]; total: number }>('/videos?liked=true&limit=10').then((r) => {
    likedVideos.value = r.items
    likedVideoCount.value = r.total
  }, () => {})
  api<{ items: Mix[] }>('/mixes').then((r) => (mixes.value = r.items), () => {})
  const [f, h] = await Promise.all([
    api<{ items: Track[] }>('/favorites').catch(() => ({ items: [] })),
    api<{ items: Track[] }>('/history?limit=1000').catch(() => ({ items: [] })),
  ])
  favorites.value = f.items
  historyCount.value = new Set(h.items.map((x) => x.id)).size
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
        <button type="button" class="flex h-[34px] items-center gap-1 rounded-full border border-line-strong px-3.5 text-sm" @click="(newName = ''), (creating = 'songs')">
          <Plus :size="16" :stroke-width="1.6" />{{ t('playlists.new') }}
        </button>
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
    <section v-if="likedVideos.length" class="flex flex-col gap-3">
      <RouterLink :to="{ name: 'favorites', query: { tab: 'videos' } }" class="flex items-center gap-1 self-start text-[22px] font-bold">
        {{ t('favorites.likedVideos') }} <span class="text-[15px] font-normal text-muted">{{ likedVideoCount }}</span><ChevronRight :size="20" :stroke-width="1.6" />
      </RouterLink>
      <ul class="-mx-5 flex gap-3 overflow-x-auto px-5 pb-1 [scrollbar-width:none] md:mx-0 md:px-0">
        <li v-for="(v, i) in likedVideos" :key="v.id" class="w-[200px] flex-none md:w-[240px]">
          <button type="button" class="group flex w-full flex-col gap-1.5 text-left" :aria-label="`${t('videos.play')}: ${v.title}`" @click="ui.videoQueue = { items: likedVideos, start: i, title: t('favorites.likedVideos') }">
            <span class="relative block aspect-video w-full overflow-hidden rounded-xl bg-surface"><VideoThumb :video="v" /></span>
            <span class="line-clamp-2 text-[14px] leading-snug">{{ v.title }}</span>
          </button>
        </li>
      </ul>
    </section>

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
