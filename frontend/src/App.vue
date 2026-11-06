<script setup lang="ts">
import { computed, nextTick, provide, reactive, ref, watch } from 'vue'
import { isNavigationFailure, NavigationFailureType, useRoute, useRouter, type RouteLocationRaw } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ArrowLeft, ArrowRight, BookHeadphones, ChartNoAxesColumn, Clapperboard, ChevronLeft, ChevronUp, Heart, History, House, LibraryBig, ListMusic, ListVideo, PanelLeftClose, PanelLeftOpen, Radio, RefreshCw, Search, User, Users } from '@lucide/vue'
import { api, setUnauthorizedHandler } from './api'
import { appConfig } from './config'
import { coverGlow } from './coverColor'
import { forgetListSearches, listSearchFor } from './listSearch'
import { useOverlayHistory } from './overlayHistory'
import { openPlayer } from './playerNav'
import { PAGE_BACK } from './pageBack'
import { PULL, usePullRefresh } from './pullRefresh'
import { useSiblingSwipe } from './siblingSwipe'
import { useWakeLock } from './wakeLock'
import { goBack, LIBRARY_ROUTES } from './router'
import { useAuth } from './stores/auth'
import { useLibrary } from './stores/library'
import { usePlayer } from './stores/player'
import { connectNative } from './native'
import { startPrefsSync } from './prefsSync'
import { useUi } from './stores/ui'
import AccountMenu from './components/AccountMenu.vue'
import AppLogo from './components/AppLogo.vue'
import BookPlayer from './components/BookPlayer.vue'
import CoverArt from './components/CoverArt.vue'
import LivePlayer from './components/LivePlayer.vue'
import LyricsSheet from './components/LyricsSheet.vue'
import NowPlaying from './components/NowPlaying.vue'
import PlayerIcons from './components/PlayerIcons.vue'
import PlayerBar from './components/PlayerBar.vue'
import PlaylistPicker from './components/PlaylistPicker.vue'
import VideoSheet from './components/VideoSheet.vue'
import QueuePanel from './components/QueuePanel.vue'
import SearchBox from './components/SearchBox.vue'
import VideoPlayer from './components/VideoPlayer.vue'
import VideoPlaylistPicker from './components/VideoPlaylistPicker.vue'
import VideoLinkSheet from './components/VideoLinkSheet.vue'
import StationBadge from './components/StationBadge.vue'
import SwipeHint from './components/SwipeHint.vue'

const { t } = useI18n()
const auth = useAuth()
const library = useLibrary()
const player = usePlayer()
const ui = useUi()
connectNative() // inside the Windows app: its tray and shortcuts (native.ts)
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
const KEPT = ['SearchView', 'AlbumsView', 'ArtistsView', 'TracksView', 'GenresView', 'FoldersView', 'CollectionsView', 'ChartsView', 'BooksView', 'MixView']
const KEPT_ROUTES = ['search', 'albums', 'artists', 'tracks', 'genres', 'folders', 'charts', 'chart-list', 'books', 'mix']
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
    forgetListSearches()
    if (id) {
      player.restore(id)
      library.loadPlaylists().catch(() => {})
      library.loadVideoPlaylists().catch(() => {})
    }
  },
  { immediate: true },
)
// the settings page's choices, the same on every device (kept with the account); after the player's
// own were read back above, so the account's newer ones win
startPrefsSync()
if (ui.playerPrefs.startMinimized) ui.barHidden = true // Settings → player: start with the mini player tucked away

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
    ui.videoQueue = null
  },
)

// phone: pulled down from the top, the page loads again (the lists kept alive too); music plays on
const refresher = usePullRefresh(mainEl, () => {
  keepKey.value++
  scrolls.clear()
  ui.libraryCheckedAt = 0
  library.loadPlaylists().catch(() => {})
  library.loadVideoPlaylists().catch(() => {})
})

// phone: on a page opened from a list, a sideways swipe opens the next / previous one of that list
const swiper = useSiblingSwipe(mainEl)

router.beforeEach((_to, from) => {
  if (mainEl.value) scrolls.set(from.fullPath, mainEl.value.scrollTop)
})
useOverlayHistory(router, [
  { open: () => ui.playerOpen, close: () => (ui.playerOpen = false) },
  { open: () => ui.queueOpen, close: () => (ui.queueOpen = false) },
  { open: () => !!ui.playlistPicker, close: () => (ui.playlistPicker = null) },
  { open: () => !!ui.videoTarget, close: () => (ui.videoTarget = null) },
  { open: () => !!ui.lyricsTarget, close: () => (ui.lyricsTarget = null) },
  { open: () => !!ui.videoPick, close: () => (ui.videoPick = null) },
  { open: () => !!ui.videoLink, close: () => (ui.videoLink = null) },
  { open: () => !!ui.videoQueue, close: () => (ui.videoQueue = null) },
])

router.afterEach(async (to, from, failure) => {
  // a link to the page already showing (e.g. the album, from the player over it) still closes the sheets
  if (isNavigationFailure(failure, NavigationFailureType.duplicated)) {
    ui.playerOpen = false
    ui.queueOpen = false
  }
  if (failure || to.fullPath === from.fullPath) return // e.g. back closing a sheet: the page stays as it is
  // (a genre's songs is a page of its own, without the tabs: not a place to come back to)
  if (LIBRARY_ROUTES.includes(to.name as (typeof LIBRARY_ROUTES)[number]) && !to.query.genre) ui.views = { ...ui.views, library: to.fullPath }
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

// the library menu (albums, artists, songs, genres, folders) opens on the tab used last
const inLibrary = computed(() => LIBRARY_ROUTES.includes(route.name as (typeof LIBRARY_ROUTES)[number]))

// on the audiobook list the top bar searches the audiobooks, on a library tab that tab alone, as it
// is typed (those pages have no search box of their own on wide screens); everywhere else, music
const searchBooks = computed(() => route.name === 'books')
const searchTab = computed(() => inLibrary.value && !(route.name === 'tracks' && route.query.genre))
const tabSearch = listSearchFor(() => String(route.name))
const topSearch = computed({
  get: () => (searchTab.value ? tabSearch.value : searchText.value),
  set: (v: string) => (searchTab.value ? (tabSearch.value = v) : (searchText.value = v)),
})
const TAB_ONLY: Record<string, 'album' | 'artist' | 'track'> = { albums: 'album', artists: 'artist', tracks: 'track' }
function search() {
  const q = searchText.value.trim()
  if (searchTab.value) return
  if (searchBooks.value) router.replace({ query: { ...route.query, q: q || undefined } })
  else if (q) router.push({ name: 'search', query: { q } })
}
const libraryItem = computed(() => ({ key: 'library', to: ui.views.library || '/albums', label: 'nav.libraryMenu', icon: LibraryBig }))
const books = { key: 'books', to: '/books', label: 'nav.audiobooks', icon: BookHeadphones }
const sideNav = computed(() => [
  { key: 'home', to: '/', label: 'nav.home', icon: House },
  { key: 'explore', to: '/search', label: 'nav.search', icon: Search },
  libraryItem.value,
  { key: 'charts', to: '/charts', label: 'nav.charts', icon: ChartNoAxesColumn },
  { key: 'radio', to: '/radio', label: 'nav.radio', icon: Radio },
  { key: 'videos', to: '/videos', label: 'nav.videos', icon: Clapperboard },
  ...(appConfig.audiobooks ? [books] : []),
  { key: 'favorites', to: '/favorites', label: 'nav.favorites', icon: Heart },
  { key: 'history', to: '/history', label: 'nav.history', icon: History },
  { key: 'mymusic', to: '/library', label: 'nav.myMusic', icon: User },
])
// (phone) my music before the library
const tabs = computed(() => [
  { key: 'home', to: '/', label: 'nav.home', icon: House },
  { key: 'mymusic', to: '/library', label: 'nav.myMusic', icon: User },
  libraryItem.value,
  { key: 'charts', to: '/charts', label: 'nav.charts', icon: ChartNoAxesColumn },
  { key: 'radio', to: '/radio', label: 'nav.radio', icon: Radio },
  { key: 'videos', to: '/videos', label: 'nav.videos', icon: Clapperboard },
  ...(appConfig.audiobooks ? [books] : []),
  { key: 'explore', to: '/search', label: 'nav.explore', icon: Search },
])
const myMusicPaths = ['/library', '/favorites', '/history', '/playlists', '/video-playlists', '/settings', '/admin']
function active(key: string, to: string) {
  if (key === 'library') return inLibrary.value
  if (key === 'home') return route.path === '/'
  if (key === 'mymusic') return myMusicPaths.some((p) => route.path.startsWith(p))
  if (key === 'explore') return route.path.startsWith('/search')
  return route.path.startsWith(to)
}

// the phone tab bar scrolls sideways when the tabs don't fit: keep the current one in view
const tabBar = ref<HTMLElement | null>(null)
watch(
  () => route.path,
  async () => {
    await nextTick()
    tabBar.value?.querySelector('[aria-current="page"]')?.scrollIntoView({ inline: 'nearest', block: 'nearest' })
  },
)

// back / forward: arrows in the PC top bar; on phones a back button above pages below the tabs
// (an installed app has no browser buttons). Read again on every page change.
const canBack = computed(() => (route.fullPath, !!window.history.state?.back))
const canForward = computed(() => (route.fullPath, !!window.history.state?.forward))
const TOP_PAGES = ['home', 'albums', 'artists', 'tracks', 'genres', 'folders', 'books', 'library', 'search']
const showBack = computed(
  () => !TOP_PAGES.includes(String(route.name)) || (route.name === 'folders' && !!route.query.path) || (route.name === 'tracks' && !!route.query.genre),
)
// where back goes when there is no earlier page (opened from a link or after a reload)
function parentPage(): RouteLocationRaw {
  const path = typeof route.query.path === 'string' ? route.query.path : ''
  if (route.name === 'folders' && path.includes('/')) return { name: 'folders', query: { path: path.slice(0, path.lastIndexOf('/')) } }
  if (route.name === 'settings' && route.params.section) return '/settings' // a part of Settings: its menu
  if (route.name === 'admin' && route.params.section) return '/admin' // a part of Admin (phones): its menu
  const parents: Record<string, string> = {
    album: '/albums', artist: '/artists', folders: '/folders', tracks: '/genres', playlist: '/playlists', chart: '/charts',
    'chart-list': '/charts', book: '/books', mix: '/library', playlists: '/library', favorites: '/library', history: '/library',
    settings: '/library', admin: '/library', stats: '/admin', logs: '/admin',
  }
  return parents[String(route.name)] ?? '/'
}
// a page with a big title shows back on the title's line (PageHeader); others get App's back line
const headerBacks = reactive(new Set<number>())
provide(PAGE_BACK, { show: showBack, go: () => goBack(parentPage()), owners: headerBacks })

// Settings → player: open the player when a list starts playing; keep the screen on while it's open
// a tucked-away player bar comes back when something starts playing
watch(() => [player.playStarts, player.playing] as const, ([, playing], [startsBefore]) => {
  if (playing || player.playStarts !== startsBefore) ui.barHidden = false
})
watch(() => player.playStarts, () => {
  if (ui.playerPrefs.openOnPlay && player.mode === 'music' && !ui.playerOpen && route.name !== 'playing') openPlayer()
})
watch(() => ui.playerPrefs.musicSpeed, (on) => {
  if (!on) player.musicRate = 1 // speed control turned off: back to normal speed
})
useWakeLock(() => ui.playerPrefs.keepAwake && player.playing && (ui.playerOpen || route.name === 'playing'))

// Plexamp-style and modern dark themes: the playing song's cover colour tints the page background
const ambient = ref('')
watch(
  () => [ui.theme, player.current?.album_id, player.current?.cover_v, player.current?.has_cover] as const,
  async ([theme, albumId, v, hasCover]) => {
    ambient.value = (theme === 'plexamp' || theme === 'spotify') && albumId && hasCover ? ((await coverGlow(albumId, v)) ?? '') : ''
  },
  { immediate: true },
)
// the PC player page keeps the bar (it holds the controls)
const barHidden = computed(() => ui.barHidden && route.name !== 'playing')
</script>

<template>
  <RouterView v-if="isPublic" />

  <div v-else-if="auth.user" class="ambient flex h-dvh bg-bg" :style="ambient ? { '--ambient': ambient } : undefined">
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
        :key="item.key"
        :to="item.to"
        class="flex h-11 flex-none items-center gap-3 rounded-full text-base"
        :class="[
          (item.key === 'mymusic' ? route.path === '/library' : active(item.key, item.to)) ? 'bg-surface-2 font-medium' : 'font-light hover:bg-surface',
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
        :class="active('playlists', '/playlists') ? 'bg-surface-2' : ''"
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
        v-for="p in ui.sidebarCollapsed ? [] : library.playlists.slice(0, 10)"
        :key="p.id"
        :to="{ name: 'playlist', params: { id: p.id } }"
        class="flex h-9 flex-none items-center truncate rounded-full px-3.5 text-[15px]"
        :class="route.name === 'playlist' && route.params.id === String(p.id) ? 'bg-surface-2' : 'font-light hover:bg-surface'"
      >
        <span class="truncate">{{ p.name }}</span>
      </RouterLink>
      <div v-if="!ui.sidebarCollapsed" class="mx-3.5 mb-1 mt-5 flex items-center justify-between text-[13px] text-muted">
        <RouterLink :to="{ path: '/playlists', hash: '#video-playlists' }" class="hover:text-ink">{{ t('videos.myVideoPlaylists') }}</RouterLink>
        <ListVideo :size="16" :stroke-width="1.4" />
      </div>
      <RouterLink
        v-for="p in ui.sidebarCollapsed ? [] : library.videoPlaylists.slice(0, 10)"
        :key="`v${p.id}`"
        :to="{ name: 'video-playlist', params: { id: p.id } }"
        class="flex h-9 flex-none items-center truncate rounded-full px-3.5 text-[15px]"
        :class="route.name === 'video-playlist' && route.params.id === String(p.id) ? 'bg-surface-2' : 'font-light hover:bg-surface'"
      >
        <span class="truncate">{{ p.name }}</span>
      </RouterLink>
      <div class="flex-1" />
      <RouterLink
        v-if="auth.user.is_admin"
        to="/admin"
        class="flex h-11 flex-none items-center gap-3 rounded-full text-[15px]"
        :class="[active('admin', '/admin') ? 'bg-surface-2 font-medium' : 'font-light hover:bg-surface', ui.sidebarCollapsed ? 'justify-center' : 'px-3.5']"
        :title="ui.sidebarCollapsed ? t('nav.admin') : undefined"
        :aria-label="ui.sidebarCollapsed ? t('nav.admin') : undefined"
      >
        <Users :size="20" :stroke-width="1.4" class="flex-none" /><span v-if="!ui.sidebarCollapsed">{{ t('nav.admin') }}</span>
      </RouterLink>
      <!-- the person: switch accounts, devices, settings, sign out -->
      <AccountMenu variant="sidebar" :collapsed="ui.sidebarCollapsed" class="mt-1 flex-none" />
    </nav>

    <div class="relative flex min-w-0 flex-1 flex-col">
      <!-- desktop top bar -->
      <header class="hidden items-center justify-between gap-4 px-12 pb-1 pt-6 md:flex">
        <div class="flex flex-none items-center gap-1.5">
          <button type="button" class="grid size-10 place-items-center rounded-full bg-surface disabled:opacity-40" :disabled="!canBack && !showBack" :aria-label="t('nav.back')" :title="t('nav.back')" @click="goBack(parentPage())">
            <ArrowLeft :size="19" :stroke-width="1.6" />
          </button>
          <button type="button" class="grid size-10 place-items-center rounded-full bg-surface disabled:opacity-40" :disabled="!canForward" :aria-label="t('nav.forward')" :title="t('nav.forward')" @click="router.forward()">
            <ArrowRight :size="19" :stroke-width="1.6" />
          </button>
        </div>
        <SearchBox
          id="top-search"
          v-model="topSearch"
          class="max-w-[420px] flex-1"
          :placeholder="t(searchTab ? `${String(route.name)}.search` : searchBooks ? 'books.searchPlaceholder' : 'search.placeholder')"
          :suggest="searchTab ? !!TAB_ONLY[String(route.name)] : !searchBooks"
          :only="searchTab ? TAB_ONLY[String(route.name)] : undefined"
          @submit="search"
        />
        <span class="w-[86px] flex-none" aria-hidden="true" /><!-- balances the arrows: the search box stays in the middle -->
      </header>

      <div
        v-if="refresher.pull.value > 0"
        class="pointer-events-none fixed inset-x-0 top-[calc(env(safe-area-inset-top)+6px)] z-40 flex justify-center md:hidden"
        :style="{ transform: `translateY(${refresher.pull.value - 30}px)`, opacity: Math.min(1, refresher.pull.value / PULL) }"
        aria-hidden="true"
      >
        <span class="grid size-10 place-items-center rounded-full bg-bg shadow-[0_2px_10px_rgba(0,0,0,0.18)]" :class="refresher.ready.value ? 'text-ink' : 'text-muted'">
          <RefreshCw :size="19" :stroke-width="1.8" :class="refresher.busy.value ? 'animate-spin' : ''" :style="refresher.busy.value ? undefined : { transform: `rotate(${refresher.pull.value * 4}deg)` }" />
        </span>
      </div>
      <SwipeHint :swipe="swiper" />
      <main ref="mainEl" class="min-h-0 flex-1 overflow-y-auto overscroll-y-contain px-5 pb-[calc(env(safe-area-inset-bottom)+190px)] pt-[calc(env(safe-area-inset-top)+16px)] md:px-12 md:pt-5"
        :class="barHidden ? 'md:pb-24' : 'md:pb-36'">
        <button v-if="showBack && !headerBacks.size" type="button" class="-ml-2.5 -mt-1 mb-1 grid size-11 place-items-center rounded-full md:hidden" :aria-label="t('nav.back')" @click="goBack(parentPage())">
          <ChevronLeft :size="28" :stroke-width="1.5" />
        </button>
        <RouterView v-slot="{ Component, route: r }">
          <KeepAlive :key="keepKey" :include="KEPT" :max="8">
            <component :is="Component" :key="r.fullPath" />
          </KeepAlive>
        </RouterView>
      </main>

      <!-- desktop floating player; tucked away, a small button brings it back -->
      <div v-if="!barHidden" class="pointer-events-none absolute inset-x-0 bottom-5 hidden justify-center px-8 md:flex">
        <div class="pointer-events-auto w-full max-w-[1040px]"><PlayerBar /></div>
      </div>
      <div v-else class="absolute bottom-5 right-8 hidden md:block">
        <div class="glass flex h-14 items-center gap-1 rounded-full pl-1.5 pr-1">
          <button v-if="player.current && player.mode === 'music'" type="button" class="size-11" :aria-label="t('player.open')" @click="openPlayer()">
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
        <div v-if="!ui.barHidden" class="pointer-events-auto"><PlayerBar mobile /></div>
        <!-- tucked away (swiped down): a small button brings it back -->
        <div v-else class="pointer-events-auto flex justify-end">
          <button type="button" class="glass flex h-12 items-center gap-1.5 rounded-full pl-1.5 pr-3" :aria-label="t('player.showBar')" @click="ui.barHidden = false">
            <CoverArt v-if="player.current && player.mode === 'music'" :album-id="player.current.album_id" :has-cover="player.current.has_cover" :version="player.current.cover_v" rounded="rounded-full" class="size-9" />
            <StationBadge v-else-if="player.mode === 'live' && player.station" :stn="player.station.stn" :logo="player.station.logo" class="size-9 text-[11px]" />
            <span v-else class="grid size-9 place-items-center"><PlayerIcons :name="player.playing ? 'pause' : 'play'" :size="18" :stroke="1.6" /></span>
            <ChevronUp :size="18" :stroke-width="1.6" />
          </button>
        </div>
        <nav :aria-label="t('nav.mainMenu')" class="glass pointer-events-auto h-[72px] overflow-hidden rounded-full">
          <div ref="tabBar" class="flex h-full items-center overflow-x-auto px-1.5 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
          <RouterLink
            v-for="tab in tabs"
            :key="tab.key"
            :to="tab.to"
            class="flex h-[60px] min-w-[68px] flex-1 shrink-0 flex-col items-center justify-center gap-[3px] whitespace-nowrap rounded-full px-1 text-[11px]"
            :class="active(tab.key, tab.to) ? 'bg-surface-2 font-medium' : ''"
            :aria-current="active(tab.key, tab.to) ? 'page' : undefined"
          >
            <component :is="tab.icon" :size="24" :stroke-width="active(tab.key, tab.to) ? 2 : 1.4" />{{ t(tab.label) }}
          </RouterLink>
          <AccountMenu variant="tab" class="flex-1 shrink-0" />
          </div>
        </nav>
      </div>
    </div>

    <!-- the full players come up from the bottom, the queue in from the side (style.css) -->
    <Transition name="sheet-up">
      <BookPlayer v-if="ui.playerOpen && player.mode === 'book'" />
      <LivePlayer v-else-if="ui.playerOpen && player.mode === 'live'" />
      <NowPlaying v-else-if="ui.playerOpen" />
    </Transition>
    <Transition name="panel-in" :duration="{ enter: 400, leave: 280 }">
      <QueuePanel v-if="ui.queueOpen" />
    </Transition>
    <PlaylistPicker v-if="ui.playlistPicker" />
    <LyricsSheet v-if="ui.lyricsTarget" :key="ui.lyricsTarget.trackId" />
    <VideoSheet v-if="ui.videoTarget" :key="`${ui.videoTarget.albumId}-${ui.videoTarget.trackId}`" />
    <VideoPlayer v-if="ui.videoQueue" />
    <VideoPlaylistPicker v-if="ui.videoPick" />
    <VideoLinkSheet v-if="ui.videoLink" :key="ui.videoLink.id" />
  </div>

  <div
    v-if="ui.toast"
    role="status"
    class="fixed left-1/2 z-[80] w-max max-w-[calc(100vw-32px)] -translate-x-1/2 rounded-2xl px-5 py-2.5 text-sm shadow-xl"
    :class="[
      ui.toast.error ? 'bg-danger text-white' : 'bg-ink text-on-ink',
      // the full player covers the bottom with its controls: show it at the top instead
      ui.playerOpen ? 'top-[calc(env(safe-area-inset-top)+16px)]' : barHidden ? 'bottom-[calc(env(safe-area-inset-bottom)+180px)] md:bottom-24' : 'bottom-[calc(env(safe-area-inset-bottom)+180px)] md:bottom-28',
    ]"
  >
    {{ ui.toast.text }}
  </div>
</template>
