<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { BookHeadphones, ChartNoAxesColumn, ChevronUp, Disc3, Heart, History, House, ListMusic, MicVocal, Music, PanelLeftClose, PanelLeftOpen, Search, Tag, User, Users } from '@lucide/vue'
import { api, setUnauthorizedHandler } from './api'
import { appConfig } from './config'
import { useAuth } from './stores/auth'
import { useLibrary } from './stores/library'
import { usePlayer } from './stores/player'
import { useUi } from './stores/ui'
import AccountMenu from './components/AccountMenu.vue'
import AppLogo from './components/AppLogo.vue'
import BookPlayer from './components/BookPlayer.vue'
import LanguageSwitch from './components/LanguageSwitch.vue'
import CoverArt from './components/CoverArt.vue'
import NowPlaying from './components/NowPlaying.vue'
import NowPlayingDesktop from './components/NowPlayingDesktop.vue'
import PlayerIcons from './components/PlayerIcons.vue'
import PlayerBar from './components/PlayerBar.vue'
import PlaylistPicker from './components/PlaylistPicker.vue'
import VideoSheet from './components/VideoSheet.vue'
import QueuePanel from './components/QueuePanel.vue'

const { t } = useI18n()
const auth = useAuth()
const library = useLibrary()
const player = usePlayer()
const ui = useUi()
const route = useRoute()
const router = useRouter()

const searchText = ref('')
const isPublic = computed(() => !!route.meta.public)

setUnauthorizedHandler(() => {
  if (!auth.user) return
  auth.user = null
  player.reset()
  router.push({ name: 'login' })
})

// Lists stay alive when you go into an album and come back: no reload, same scroll position.
// They are dropped when the library changed (a scan, a banner), checked at most once a minute.
// (home is left out: its recently played row changes as you listen)
const KEPT = ['SearchView', 'AlbumsView', 'ArtistsView', 'TracksView', 'GenresView', 'CollectionsView', 'ChartsView', 'BooksView', 'MixView']
const KEPT_ROUTES = ['search', 'albums', 'artists', 'tracks', 'genres', 'charts', 'chart-list', 'books', 'mix']
const mainEl = ref<HTMLElement | null>(null)
const keepKey = ref(0)
const scrolls = new Map<string, number>()
let libVersion: number | null = null

// load per-user state when someone logs in, clear it on logout
watch(
  () => auth.user?.id,
  (id) => {
    library.reset()
    keepKey.value++ // nothing kept from the previous person
    scrolls.clear()
    if (id) {
      player.restore(id)
      library.loadPlaylists().catch(() => {})
    }
  },
  { immediate: true },
)

watch(
  () => route.query.q,
  (q) => (searchText.value = typeof q === 'string' ? q : ''),
  { immediate: true },
)
watch(
  () => route.fullPath,
  () => {
    ui.playerOpen = false
    ui.queueOpen = false
  },
)

router.beforeEach((_to, from) => {
  if (mainEl.value) scrolls.set(from.fullPath, mainEl.value.scrollTop)
})
router.afterEach(async (to) => {
  await nextTick()
  if (mainEl.value) mainEl.value.scrollTop = KEPT_ROUTES.includes(String(to.name)) ? scrolls.get(to.fullPath) ?? 0 : 0
  if (!auth.user || Date.now() - ui.libraryCheckedAt < 60_000) return
  ui.libraryCheckedAt = Date.now()
  const { version } = await api<{ version: number }>('/library/version').catch(() => ({ version: libVersion }))
  if (libVersion !== null && version !== libVersion) {
    keepKey.value++ // remounts the open list too, so it shows the change
    scrolls.clear()
  }
  libVersion = version
})

function search() {
  const q = searchText.value.trim()
  if (q) router.push({ name: 'search', query: { q } })
}

const books = { to: '/books', label: 'nav.audiobooks', icon: BookHeadphones }
const sideNav = computed(() => [
  { to: '/', label: 'nav.home', icon: House },
  { to: '/albums', label: 'nav.albums', icon: Disc3 },
  { to: '/artists', label: 'nav.artists', icon: MicVocal },
  { to: '/tracks', label: 'nav.songs', icon: Music },
  { to: '/genres', label: 'nav.genres', icon: Tag },
  { to: '/charts', label: 'nav.charts', icon: ChartNoAxesColumn },
  ...(appConfig.audiobooks ? [books] : []),
  { to: '/favorites', label: 'nav.favorites', icon: Heart },
  { to: '/history', label: 'nav.history', icon: History },
  { to: '/library', label: 'nav.myMusic', icon: User },
])
const tabs = computed(() => [
  { to: '/', label: 'nav.home', icon: House },
  { to: '/albums', label: 'nav.albums', icon: Disc3 },
  ...(appConfig.audiobooks ? [books] : []),
  { to: '/library', label: 'nav.myMusic', icon: User },
  { to: '/search', label: 'nav.explore', icon: Search },
  { to: '/tracks', label: 'nav.songs', icon: Music },
])
const myMusicPaths = ['/library', '/favorites', '/history', '/playlists', '/settings', '/admin']
function active(to: string) {
  if (to === '/') return route.path === '/'
  if (to === '/library') return myMusicPaths.some((p) => route.path.startsWith(p))
  if (to === '/search') return ['/search', '/genres', '/artists', '/charts'].some((p) => route.path.startsWith(p))
  return route.path.startsWith(to)
}
</script>

<template>
  <RouterView v-if="isPublic" />

  <div v-else-if="auth.user" class="flex h-dvh bg-bg">
    <!-- desktop sidebar -->
    <nav
      :aria-label="t('nav.mainMenu')"
      class="hidden flex-none flex-col gap-0.5 overflow-y-auto overflow-x-hidden border-r border-line py-7 transition-[width] duration-200 md:flex"
      :class="ui.sidebarCollapsed ? 'w-[76px] px-3' : 'w-60 px-4'"
    >
      <div class="mb-6 flex items-center" :class="ui.sidebarCollapsed ? 'flex-col gap-3' : 'justify-between pl-2.5'">
        <RouterLink to="/"><AppLogo :size="32" :wordmark="!ui.sidebarCollapsed" /></RouterLink>
        <button
          type="button"
          class="grid size-9 place-items-center rounded-full text-muted hover:bg-surface hover:text-ink"
          :aria-label="ui.sidebarCollapsed ? t('nav.expandMenu') : t('nav.collapseMenu')"
          :title="ui.sidebarCollapsed ? t('nav.expandMenu') : t('nav.collapseMenu')"
          :aria-expanded="!ui.sidebarCollapsed"
          @click="ui.sidebarCollapsed = !ui.sidebarCollapsed"
        >
          <PanelLeftOpen v-if="ui.sidebarCollapsed" :size="19" :stroke-width="1.5" />
          <PanelLeftClose v-else :size="19" :stroke-width="1.5" />
        </button>
      </div>
      <RouterLink
        v-for="item in sideNav"
        :key="item.to"
        :to="item.to"
        class="flex h-11 flex-none items-center gap-3 rounded-full text-base"
        :class="[
          (item.to === '/library' ? route.path === '/library' : active(item.to)) ? 'bg-surface-2 font-medium' : 'font-light hover:bg-surface',
          ui.sidebarCollapsed ? 'justify-center' : 'px-3.5',
        ]"
        :title="ui.sidebarCollapsed ? t(item.label) : undefined"
        :aria-label="ui.sidebarCollapsed ? t(item.label) : undefined"
      >
        <component :is="item.icon" :size="20" :stroke-width="1.4" class="flex-none" /><span v-if="!ui.sidebarCollapsed" class="truncate">{{ t(item.label) }}</span>
      </RouterLink>
      <RouterLink
        v-if="ui.sidebarCollapsed"
        to="/playlists"
        class="mt-4 flex h-11 flex-none items-center justify-center rounded-full font-light hover:bg-surface"
        :class="active('/playlists') ? 'bg-surface-2' : ''"
        :title="t('nav.playlists')"
        :aria-label="t('nav.playlists')"
      >
        <ListMusic :size="20" :stroke-width="1.4" />
      </RouterLink>
      <div v-if="!ui.sidebarCollapsed" class="mx-3.5 mb-1 mt-6 flex items-center justify-between text-[13px] text-muted">
        <RouterLink to="/playlists" class="hover:text-ink">{{ t('nav.playlists') }}</RouterLink>
        <ListMusic :size="16" :stroke-width="1.4" />
      </div>
      <RouterLink
        v-for="p in ui.sidebarCollapsed ? [] : library.playlists.slice(0, 15)"
        :key="p.id"
        :to="{ name: 'playlist', params: { id: p.id } }"
        class="flex h-9 items-center truncate rounded-full px-3.5 text-[15px]"
        :class="route.name === 'playlist' && route.params.id === String(p.id) ? 'bg-surface-2' : 'font-light hover:bg-surface'"
      >
        <span class="truncate">{{ p.name }}</span>
      </RouterLink>
      <div class="flex-1" />
      <RouterLink
        v-if="auth.user.is_admin"
        to="/admin"
        class="flex h-11 flex-none items-center gap-3 rounded-full text-[15px]"
        :class="[active('/admin') ? 'bg-surface-2 font-medium' : 'font-light hover:bg-surface', ui.sidebarCollapsed ? 'justify-center' : 'px-3.5']"
        :title="ui.sidebarCollapsed ? t('nav.admin') : undefined"
        :aria-label="ui.sidebarCollapsed ? t('nav.admin') : undefined"
      >
        <Users :size="20" :stroke-width="1.4" class="flex-none" /><span v-if="!ui.sidebarCollapsed">{{ t('nav.admin') }}</span>
      </RouterLink>
    </nav>

    <div class="relative flex min-w-0 flex-1 flex-col">
      <!-- desktop top bar -->
      <header class="hidden items-center justify-between gap-4 px-12 pb-1 pt-6 md:flex">
        <form role="search" class="flex h-[46px] max-w-[420px] flex-1 items-center gap-2.5 rounded-full bg-surface px-[18px]" @submit.prevent="search">
          <Search :size="20" :stroke-width="1.4" class="text-muted" aria-hidden="true" />
          <label for="top-search" class="sr-only">{{ t('search.label') }}</label>
          <input id="top-search" v-model="searchText" type="search" :placeholder="t('search.placeholder')" class="min-w-0 flex-1 bg-transparent text-[15px] font-light outline-none placeholder:text-muted" />
        </form>
        <div class="flex items-center gap-3">
          <LanguageSwitch compact />
          <AccountMenu avatar />
        </div>
      </header>

      <main ref="mainEl" class="min-h-0 flex-1 overflow-y-auto px-5 pb-[calc(env(safe-area-inset-bottom)+190px)] pt-[calc(env(safe-area-inset-top)+16px)] md:px-12 md:pt-5"
        :class="ui.barHidden ? 'md:pb-24' : 'md:pb-36'">
        <RouterView v-slot="{ Component, route: r }">
          <KeepAlive :key="keepKey" :include="KEPT" :max="8">
            <component :is="Component" :key="r.fullPath" />
          </KeepAlive>
        </RouterView>
      </main>

      <!-- desktop floating player; tucked away, a small button brings it back -->
      <div v-if="!ui.barHidden" class="pointer-events-none absolute inset-x-0 bottom-5 hidden justify-center px-8 md:flex">
        <div class="pointer-events-auto w-full max-w-[1040px]"><PlayerBar /></div>
      </div>
      <div v-else class="absolute bottom-5 right-8 hidden md:block">
        <div class="glass flex h-14 items-center gap-1 rounded-full pl-1.5 pr-1">
          <button v-if="player.current && player.mode === 'music'" type="button" class="size-11" :aria-label="t('player.open')" @click="ui.playerOpen = true">
            <CoverArt :album-id="player.current.album_id" :has-cover="player.current.has_cover" :version="player.current.cover_v" rounded="rounded-full" />
          </button>
          <button v-if="player.current || player.book" type="button" class="grid size-11 place-items-center rounded-full hover:bg-surface" :aria-label="player.playing ? t('player.pause') : t('player.play')" @click="player.toggle()">
            <PlayerIcons :name="player.playing ? 'pause' : 'play'" :size="22" :stroke="1.6" />
          </button>
          <button type="button" class="grid size-11 place-items-center rounded-full hover:bg-surface" :aria-label="t('player.showBar')" :title="t('player.showBar')" @click="ui.barHidden = false">
            <ChevronUp :size="20" :stroke-width="1.6" />
          </button>
        </div>
      </div>

      <!-- phone: floating mini player + tab bar -->
      <div class="bottom-safe pointer-events-none fixed inset-x-3 z-30 flex flex-col gap-2.5 md:hidden">
        <div class="pointer-events-auto"><PlayerBar mobile /></div>
        <nav :aria-label="t('nav.mainMenu')" class="glass pointer-events-auto grid h-[72px] items-center rounded-full px-1.5" :class="tabs.length > 5 ? 'grid-cols-6' : 'grid-cols-5'">
          <RouterLink
            v-for="tab in tabs"
            :key="tab.to"
            :to="tab.to"
            class="flex h-[60px] flex-col items-center justify-center gap-[3px] rounded-full text-[11px]"
            :class="active(tab.to) ? 'bg-surface-2 font-medium' : ''"
            :aria-current="active(tab.to) ? 'page' : undefined"
          >
            <component :is="tab.icon" :size="24" :stroke-width="active(tab.to) ? 2 : 1.4" />{{ t(tab.label) }}
          </RouterLink>
        </nav>
      </div>
    </div>

    <BookPlayer v-if="ui.playerOpen && player.mode === 'book'" />
    <NowPlayingDesktop v-else-if="ui.playerOpen && ui.wide" />
    <NowPlaying v-else-if="ui.playerOpen" />
    <QueuePanel v-if="ui.queueOpen" />
    <PlaylistPicker v-if="ui.playlistPicker" />
    <VideoSheet v-if="ui.videoTarget" :key="`${ui.videoTarget.albumId}-${ui.videoTarget.trackId}`" />
  </div>

  <div
    v-if="ui.toast"
    role="status"
    class="fixed left-1/2 z-[80] w-max max-w-[calc(100vw-32px)] -translate-x-1/2 rounded-2xl px-5 py-2.5 text-sm text-white shadow-xl"
    :class="[
      ui.toast.error ? 'bg-danger' : 'bg-ink',
      // the full player covers the bottom with its controls: show it at the top instead
      ui.playerOpen ? 'top-[calc(env(safe-area-inset-top)+16px)]' : ui.barHidden ? 'bottom-[calc(env(safe-area-inset-bottom)+180px)] md:bottom-24' : 'bottom-[calc(env(safe-area-inset-bottom)+180px)] md:bottom-28',
    ]"
  >
    {{ ui.toast.text }}
  </div>
</template>
