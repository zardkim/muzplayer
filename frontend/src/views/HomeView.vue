<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ListMusic } from '@lucide/vue'
import { api } from '../api'
import { useAuth } from '../stores/auth'
import { useLibrary } from '../stores/library'
import type { Album, Page, Track } from '../types'
import AlbumGrid from '../components/AlbumGrid.vue'
import TrackList from '../components/TrackList.vue'

const { t } = useI18n()
const auth = useAuth()
const library = useLibrary()
const recent = ref<Track[]>([])
const albums = ref<Album[]>([])
const loaded = ref(false)

onMounted(async () => {
  const [h, a] = await Promise.all([
    api<{ items: Track[] }>('/history?limit=50').catch(() => ({ items: [] })),
    api<Page<Album>>('/albums?sort=recent&limit=12').catch(() => ({ items: [], total: 0 })),
  ])
  // one entry per track, most recent first
  const seen = new Set<number>()
  recent.value = h.items.filter((x) => !seen.has(x.id) && seen.add(x.id)).slice(0, 8)
  albums.value = a.items
  loaded.value = true
})
</script>

<template>
  <div class="flex flex-col gap-10">
    <div v-if="loaded && !albums.length" class="rounded-2xl border border-line bg-surface p-8 text-center">
      <p class="font-semibold">{{ t('home.emptyLibrary') }}</p>
      <p v-if="auth.user?.is_admin" class="mt-2 text-sm text-muted">
        <RouterLink to="/admin" class="text-accent hover:text-accent-strong">{{ t('home.emptyLibraryAdmin') }}</RouterLink>
      </p>
    </div>

    <section v-if="albums.length" class="flex flex-col gap-4">
      <div class="flex items-baseline justify-between">
        <h2 class="text-xl font-bold">{{ t('home.newAlbums') }}</h2>
        <RouterLink to="/albums" class="text-[13px] text-muted hover:text-ink">{{ t('common.viewAll') }}</RouterLink>
      </div>
      <AlbumGrid :albums="albums" row />
    </section>

    <section v-if="recent.length" class="flex flex-col gap-2">
      <div class="flex items-baseline justify-between">
        <h2 class="text-xl font-bold">{{ t('home.recent') }}</h2>
        <RouterLink to="/history" class="text-[13px] text-muted hover:text-ink">{{ t('common.viewAll') }}</RouterLink>
      </div>
      <TrackList :tracks="recent" />
    </section>

    <section v-if="library.playlists.length" class="flex flex-col gap-1 md:hidden">
      <h2 class="mb-2 text-xl font-bold">{{ t('home.myPlaylists') }}</h2>
      <RouterLink v-for="p in library.playlists.slice(0, 5)" :key="p.id" :to="{ name: 'playlist', params: { id: p.id } }" class="flex min-h-[60px] items-center gap-3.5">
        <span class="grid size-[52px] flex-none place-items-center rounded-[10px] bg-surface-2 text-accent"><ListMusic :size="22" /></span>
        <span class="flex flex-col">
          <span class="text-[15px] font-semibold">{{ p.name }}</span>
          <span class="text-[13px] text-muted">{{ t('common.tracks', p.track_count) }}</span>
        </span>
      </RouterLink>
    </section>
  </div>
</template>
