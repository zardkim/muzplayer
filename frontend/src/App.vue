<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { BookHeadphones, ChartNoAxesColumn, Disc3, Heart, History, House, ListMusic, MicVocal, Music, Search, Tag, User, Users } from '@lucide/vue'
import { setUnauthorizedHandler } from './api'
import { appConfig } from './config'
import { useAuth } from './stores/auth'
import { useLibrary } from './stores/library'
import { usePlayer } from './stores/player'
import { useUi } from './stores/ui'
import AccountMenu from './components/AccountMenu.vue'
import AppLogo from './components/AppLogo.vue'
import BookPlayer from './components/BookPlayer.vue'
import LanguageSwitch from './components/LanguageSwitch.vue'
import NowPlaying from './components/NowPlaying.vue'
import PlayerBar from './components/PlayerBar.vue'
import PlaylistPicker from './components/PlaylistPicker.vue'
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

// load per-user state when someone logs in, clear it on logout
watch(
  () => auth.user?.id,
  (id) => {
    library.reset()
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
    <nav :aria-label="t('nav.mainMenu')" class="hidden w-60 flex-none flex-col gap-0.5 overflow-y-auto border-r border-line px-4 py-7 md:flex">
      <RouterLink to="/" class="mb-6 px-2.5"><AppLogo :size="32" /></RouterLink>
      <RouterLink
        v-for="item in sideNav"
        :key="item.to"
        :to="item.to"
        class="flex h-11 items-center gap-3 rounded-full px-3.5 text-base"
        :class="(item.to === '/library' ? route.path === '/library' : active(item.to)) ? 'bg-surface-2 font-medium' : 'font-light hover:bg-surface'"
      >
        <component :is="item.icon" :size="20" :stroke-width="1.4" />{{ t(item.label) }}
      </RouterLink>
      <div class="mx-3.5 mb-1 mt-6 flex items-center justify-between text-[13px] text-muted">
        <RouterLink to="/playlists" class="hover:text-ink">{{ t('nav.playlists') }}</RouterLink>
        <ListMusic :size="16" :stroke-width="1.4" />
      </div>
      <RouterLink
        v-for="p in library.playlists.slice(0, 15)"
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
        class="flex h-11 items-center gap-3 rounded-full px-3.5 text-[15px]"
        :class="active('/admin') ? 'bg-surface-2 font-medium' : 'font-light hover:bg-surface'"
      >
        <Users :size="20" :stroke-width="1.4" />{{ t('nav.admin') }}
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

      <main class="min-h-0 flex-1 overflow-y-auto px-5 pb-[calc(env(safe-area-inset-bottom)+190px)] pt-[calc(env(safe-area-inset-top)+16px)] md:px-12 md:pb-36 md:pt-5">
        <RouterView :key="route.fullPath" />
      </main>

      <!-- desktop floating player -->
      <div class="pointer-events-none absolute inset-x-0 bottom-5 hidden justify-center px-8 md:flex">
        <div class="pointer-events-auto w-full max-w-[1040px]"><PlayerBar /></div>
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
    <NowPlaying v-else-if="ui.playerOpen" />
    <QueuePanel v-if="ui.queueOpen" />
    <PlaylistPicker v-if="ui.playlistPicker" />
  </div>

  <div
    v-if="ui.toast"
    role="status"
    class="fixed left-1/2 z-[80] w-max max-w-[calc(100vw-32px)] -translate-x-1/2 rounded-2xl px-5 py-2.5 text-sm text-white shadow-xl"
    :class="[
      ui.toast.error ? 'bg-danger' : 'bg-ink',
      // the full player covers the bottom with its controls: show it at the top instead
      ui.playerOpen ? 'top-[calc(env(safe-area-inset-top)+16px)]' : 'bottom-[calc(env(safe-area-inset-bottom)+180px)] md:bottom-28',
    ]"
  >
    {{ ui.toast.text }}
  </div>
</template>
