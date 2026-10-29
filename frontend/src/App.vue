<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Disc3, Ellipsis, Heart, History, House, Library, ListMusic, LogOut, MicVocal, Music, Search, Settings, Tag, Users } from '@lucide/vue'
import { setUnauthorizedHandler } from './api'
import { useAuth } from './stores/auth'
import { useLibrary } from './stores/library'
import { usePlayer } from './stores/player'
import { useUi } from './stores/ui'
import AppLogo from './components/AppLogo.vue'
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
const accountOpen = ref(false)
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
    accountOpen.value = false
    ui.playerOpen = false
  },
)

function search() {
  const q = searchText.value.trim()
  if (q) router.push({ name: 'search', query: { q } })
}

async function logout() {
  player.reset()
  await auth.logout()
  router.push({ name: 'login' })
}

const mainNav = [
  { to: '/', label: 'nav.home', icon: House },
  { to: '/tracks', label: 'nav.tracks', icon: Music },
  { to: '/albums', label: 'nav.albums', icon: Disc3 },
  { to: '/artists', label: 'nav.artists', icon: MicVocal },
  { to: '/genres', label: 'nav.genres', icon: Tag },
  { to: '/favorites', label: 'nav.favorites', icon: Heart },
  { to: '/history', label: 'nav.history', icon: History },
  { to: '/playlists', label: 'nav.playlists', icon: ListMusic },
]
const tabs = [
  { to: '/', label: 'nav.home', icon: House },
  { to: '/albums', label: 'nav.albums', icon: Disc3 },
  { to: '/search', label: 'nav.search', icon: Search },
  { to: '/playlists', label: 'nav.library', icon: Library },
  { to: '/more', label: 'nav.more', icon: Ellipsis },
]
function active(to: string) {
  return to === '/' ? route.path === '/' : route.path.startsWith(to)
}
const initial = computed(() => (auth.user?.display_name || auth.user?.username || '?').slice(0, 1).toUpperCase())
</script>

<template>
  <RouterView v-if="isPublic" />

  <div v-else-if="auth.user" class="flex h-dvh flex-col">
    <div class="flex min-h-0 flex-1">
      <!-- desktop sidebar -->
      <nav :aria-label="t('nav.mainMenu')" class="hidden w-60 flex-none flex-col gap-1 overflow-y-auto border-r border-[#1E2228] bg-sidebar px-4 py-6 md:flex">
        <RouterLink to="/" class="mb-5 px-2.5"><AppLogo :size="32" /></RouterLink>
        <RouterLink
          v-for="item in mainNav"
          :key="item.to"
          :to="item.to"
          class="flex h-11 items-center gap-3 rounded-[10px] px-3 text-[15px]"
          :class="active(item.to) ? 'bg-surface-2 font-semibold text-ink' : 'text-muted hover:text-ink'"
        >
          <component :is="item.icon" :size="20" />{{ t(item.label) }}
        </RouterLink>
        <RouterLink
          v-for="p in library.playlists.slice(0, 12)"
          :key="p.id"
          :to="{ name: 'playlist', params: { id: p.id } }"
          class="flex h-9 items-center truncate rounded-lg pl-11 pr-3 text-sm"
          :class="route.name === 'playlist' && route.params.id === String(p.id) ? 'text-ink' : 'text-muted hover:text-ink'"
        >
          <span class="truncate">{{ p.name }}</span>
        </RouterLink>
        <div class="flex-1" />
        <RouterLink
          v-if="auth.user.is_admin"
          to="/admin"
          class="flex h-11 items-center gap-3 rounded-[10px] px-3 text-sm"
          :class="active('/admin') ? 'bg-surface-2 font-semibold text-ink' : 'text-muted hover:text-ink'"
        >
          <Users :size="20" />{{ t('nav.admin') }}
        </RouterLink>
      </nav>

      <div class="flex min-w-0 flex-1 flex-col">
        <!-- top bar -->
        <header class="flex items-center justify-between gap-3 px-5 pb-2 pt-4 md:px-10 md:pt-6">
          <RouterLink to="/" class="md:hidden"><AppLogo :size="28" /></RouterLink>
          <form role="search" class="hidden h-11 max-w-[420px] flex-1 items-center gap-2.5 rounded-full border border-line bg-surface px-3.5 md:flex" @submit.prevent="search">
            <Search :size="18" class="text-muted" aria-hidden="true" />
            <label for="top-search" class="sr-only">{{ t('search.label') }}</label>
            <input id="top-search" v-model="searchText" type="search" :placeholder="t('search.placeholder')" class="min-w-0 flex-1 bg-transparent text-[15px] outline-none placeholder:text-subtle" />
          </form>
          <div class="relative flex items-center gap-3">
            <div class="hidden md:block"><LanguageSwitch compact /></div>
            <button
              type="button"
              class="grid size-10 place-items-center rounded-full bg-[#2D4A6B] font-semibold"
              :aria-label="t('nav.accountMenu')"
              :aria-expanded="accountOpen"
              @click="accountOpen = !accountOpen"
            >
              {{ initial }}
            </button>
            <div v-if="accountOpen" class="absolute right-0 top-12 z-30 flex w-56 flex-col overflow-hidden rounded-xl border border-line bg-surface-2 py-1 text-sm shadow-xl shadow-black/40">
              <div class="border-b border-line px-4 py-2.5">
                <div class="font-semibold">{{ auth.user.display_name }}</div>
                <div class="text-xs text-muted">{{ auth.user.username }}</div>
              </div>
              <RouterLink to="/settings" class="flex items-center gap-2 px-4 py-2.5 hover:bg-line"><Settings :size="16" />{{ t('nav.settings') }}</RouterLink>
              <RouterLink v-if="auth.user.is_admin" to="/admin" class="flex items-center gap-2 px-4 py-2.5 hover:bg-line"><Users :size="16" />{{ t('nav.admin') }}</RouterLink>
              <button type="button" class="flex items-center gap-2 px-4 py-2.5 text-left hover:bg-line" @click="logout"><LogOut :size="16" />{{ t('nav.logout') }}</button>
            </div>
          </div>
        </header>

        <main class="min-h-0 flex-1 overflow-y-auto px-5 pb-10 pt-4 md:px-10">
          <RouterView :key="route.fullPath" />
        </main>
      </div>

      <QueuePanel v-if="ui.queueOpen" />
    </div>

    <PlayerBar />

    <!-- mobile tabs -->
    <nav :aria-label="t('nav.mainMenu')" class="pb-safe grid grid-cols-5 px-1 pt-1 md:hidden">
      <RouterLink
        v-for="tab in tabs"
        :key="tab.to"
        :to="tab.to"
        class="flex flex-col items-center gap-1 py-2 text-[11px]"
        :class="active(tab.to) ? 'font-semibold text-accent' : 'text-muted'"
      >
        <component :is="tab.icon" :size="22" />{{ t(tab.label) }}
      </RouterLink>
    </nav>

    <NowPlaying v-if="ui.playerOpen" />
    <PlaylistPicker v-if="ui.playlistPicker" />
  </div>

  <div
    v-if="ui.toast"
    role="status"
    class="fixed bottom-28 left-1/2 z-[60] -translate-x-1/2 rounded-full px-5 py-2.5 text-sm shadow-xl md:bottom-28"
    :class="ui.toast.error ? 'bg-danger text-bg' : 'bg-ink text-bg'"
  >
    {{ ui.toast.text }}
  </div>
</template>
