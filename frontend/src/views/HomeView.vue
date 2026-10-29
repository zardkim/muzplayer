<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ChevronRight, ListMusic } from '@lucide/vue'
import { api } from '../api'
import { useAuth } from '../stores/auth'
import { useLibrary } from '../stores/library'
import { usePlayer } from '../stores/player'
import type { Album, Page, Track } from '../types'
import AlbumGrid from '../components/AlbumGrid.vue'
import CoverArt from '../components/CoverArt.vue'
import PageHeader from '../components/PageHeader.vue'
import PlayerIcons from '../components/PlayerIcons.vue'

const { t } = useI18n()
const auth = useAuth()
const library = useLibrary()
const player = usePlayer()
const history = ref<Track[]>([])
const albums = ref<Album[]>([])
const loaded = ref(false)
const tab = ref<'recent' | 'new' | 'playlists'>('recent')

onMounted(async () => {
  const [h, a] = await Promise.all([
    api<{ items: Track[] }>('/history?limit=100').catch(() => ({ items: [] })),
    api<Page<Album>>('/albums?sort=recent&limit=12').catch(() => ({ items: [], total: 0 })),
  ])
  history.value = h.items
  albums.value = a.items
  loaded.value = true
})

// recently played, grouped by album so the list reads like "what was I listening to"
const recentAlbums = computed(() => {
  const seen = new Set<number>()
  const out: Track[] = []
  for (const tr of history.value) {
    const key = tr.album_id ?? -tr.id
    if (seen.has(key)) continue
    seen.add(key)
    out.push(tr)
    if (out.length === 6) break
  }
  return out
})

const tabs = computed(() => [
  { key: 'recent' as const, label: t('home.tabRecent') },
  { key: 'new' as const, label: t('home.tabNew') },
  { key: 'playlists' as const, label: t('home.tabPlaylists') },
])
</script>

<template>
  <div class="flex flex-col gap-7">
    <PageHeader :title="t('nav.home')" />

    <div class="-mr-5 flex gap-2 overflow-x-auto pr-5 [scrollbar-width:none]">
      <button
        v-for="x in tabs"
        :key="x.key"
        type="button"
        class="h-[38px] flex-none rounded-full border px-4 text-[15px]"
        :class="tab === x.key ? 'border-ink bg-ink text-white' : 'border-line-strong bg-bg'"
        @click="tab = x.key"
      >
        {{ x.label }}
      </button>
    </div>

    <div v-if="loaded && !albums.length" class="rounded-2xl bg-surface p-8 text-center">
      <p class="font-medium">{{ t('home.emptyLibrary') }}</p>
      <p v-if="auth.user?.is_admin" class="mt-2 text-sm">
        <RouterLink to="/admin" class="text-accent underline">{{ t('home.emptyLibraryAdmin') }}</RouterLink>
      </p>
    </div>

    <!-- quick list -->
    <section v-if="tab === 'recent'" class="flex flex-col gap-3.5">
      <p v-if="loaded && !recentAlbums.length" class="font-light text-muted">{{ t('home.nothingRecent') }}</p>
      <div v-for="tr in recentAlbums" :key="tr.id" class="flex items-center gap-3.5">
        <RouterLink :to="tr.album_id ? { name: 'album', params: { id: tr.album_id } } : { name: 'history' }" class="flex min-w-0 flex-1 items-center gap-3.5">
          <CoverArt :album-id="tr.album_id" :has-cover="tr.has_cover" rounded="rounded-lg" class="size-[60px] flex-none" />
          <span class="flex min-w-0 flex-col">
            <span class="truncate text-[17px]">{{ tr.album || tr.title }}</span>
            <span class="truncate text-sm font-light text-muted">{{ tr.artist || t('common.unknownArtist') }}</span>
          </span>
        </RouterLink>
        <button
          type="button"
          class="grid size-11 place-items-center"
          :aria-label="`${t('common.play')}: ${tr.album || tr.title}`"
          @click="tr.album_id ? player.playAlbum(tr.album_id) : player.playTracks([tr])"
        >
          <PlayerIcons name="play" :size="26" :stroke="1.3" />
        </button>
      </div>
    </section>
    <section v-else-if="tab === 'new'">
      <AlbumGrid :albums="albums" />
    </section>
    <section v-else class="flex flex-col gap-3">
      <p v-if="!library.playlists.length" class="font-light text-muted">{{ t('playlists.empty') }}</p>
      <RouterLink v-for="p in library.playlists" :key="p.id" :to="{ name: 'playlist', params: { id: p.id } }" class="flex items-center gap-3.5">
        <span class="grid size-[60px] flex-none place-items-center rounded-lg bg-surface"><ListMusic :size="24" :stroke-width="1.3" /></span>
        <span class="flex flex-col">
          <span class="text-[17px]">{{ p.name }}</span>
          <span class="text-sm font-light text-muted">{{ t('common.tracks', p.track_count) }}</span>
        </span>
      </RouterLink>
    </section>

    <section v-if="albums.length && tab !== 'new'" class="mt-3 flex flex-col gap-4">
      <RouterLink to="/albums" class="flex items-center gap-1 text-[22px] font-bold">{{ t('home.newAlbums') }} <ChevronRight :size="22" :stroke-width="1.6" /></RouterLink>
      <AlbumGrid :albums="albums" row />
    </section>
  </div>
</template>
