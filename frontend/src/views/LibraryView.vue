<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ChevronRight, Clock, Heart, ListMusic, MicVocal, Plus, Settings, Tag, Users } from '@lucide/vue'
import { api } from '../api'
import { errorMessage } from '../i18n'
import { useAuth } from '../stores/auth'
import { useLibrary } from '../stores/library'
import { usePlayer } from '../stores/player'
import { useUi } from '../stores/ui'
import type { Genre, Page, Artist, Track } from '../types'
import BaseModal from '../components/BaseModal.vue'
import CoverArt from '../components/CoverArt.vue'
import PageHeader from '../components/PageHeader.vue'

const { t } = useI18n()
const auth = useAuth()
const library = useLibrary()
const player = usePlayer()
const ui = useUi()
const router = useRouter()

const favorites = ref<Track[]>([])
const historyCount = ref(0)
const artistCount = ref(0)
const genreCount = ref(0)

onMounted(async () => {
  library.loadPlaylists().catch(() => {})
  const [f, h, a, g] = await Promise.all([
    api<{ items: Track[] }>('/favorites').catch(() => ({ items: [] })),
    api<{ items: Track[] }>('/history?limit=1000').catch(() => ({ items: [] })),
    api<Page<Artist>>('/artists?limit=1').catch(() => ({ items: [], total: 0 })),
    api<{ items: Genre[] }>('/genres').catch(() => ({ items: [] })),
  ])
  favorites.value = f.items
  historyCount.value = new Set(h.items.map((x) => x.id)).size
  artistCount.value = a.total
  genreCount.value = g.items.length
})

const creating = ref(false)
const newName = ref('')
async function create() {
  if (!newName.value.trim()) return
  try {
    const p = await library.createPlaylist(newName.value.trim())
    creating.value = false
    router.push({ name: 'playlist', params: { id: p.id } })
  } catch (e) {
    ui.notify(errorMessage(e), true)
  }
}
</script>

<template>
  <div class="flex flex-col gap-6">
    <PageHeader :title="t('library.title')" />

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
          :has-cover="f.has_cover"
          rounded="rounded-full"
          class="size-10 border-2 border-white"
          :class="i ? '-ml-3' : ''"
        />
      </span>
    </button>

    <nav class="flex flex-col">
      <RouterLink to="/favorites" class="flex h-[58px] items-center gap-4">
        <Heart :size="26" :stroke-width="1.2" /><span class="flex-1 text-lg font-light">{{ t('nav.favorites') }}</span>
        <span class="text-[15px] font-light text-muted">{{ t('library.tracksCount', { n: favorites.length }) }}</span><ChevronRight :size="18" class="text-subtle" />
      </RouterLink>
      <RouterLink to="/history" class="flex h-[58px] items-center gap-4">
        <Clock :size="26" :stroke-width="1.2" /><span class="flex-1 text-lg font-light">{{ t('nav.history') }}</span>
        <span class="text-[15px] font-light text-muted">{{ t('library.tracksCount', { n: historyCount }) }}</span><ChevronRight :size="18" class="text-subtle" />
      </RouterLink>
      <RouterLink to="/artists" class="flex h-[58px] items-center gap-4">
        <MicVocal :size="26" :stroke-width="1.2" /><span class="flex-1 text-lg font-light">{{ t('nav.artists') }}</span>
        <span class="text-[15px] font-light text-muted">{{ t('library.artistsCount', { n: artistCount }) }}</span><ChevronRight :size="18" class="text-subtle" />
      </RouterLink>
      <RouterLink to="/genres" class="flex h-[58px] items-center gap-4">
        <Tag :size="26" :stroke-width="1.2" /><span class="flex-1 text-lg font-light">{{ t('nav.genres') }}</span>
        <span class="text-[15px] font-light text-muted">{{ t('library.genresCount', { n: genreCount }) }}</span><ChevronRight :size="18" class="text-subtle" />
      </RouterLink>
      <RouterLink to="/settings" class="flex h-[58px] items-center gap-4">
        <Settings :size="26" :stroke-width="1.2" /><span class="flex-1 text-lg font-light">{{ t('nav.settings') }}</span><ChevronRight :size="18" class="text-subtle" />
      </RouterLink>
      <RouterLink v-if="auth.user?.is_admin" to="/admin" class="flex h-[58px] items-center gap-4">
        <Users :size="26" :stroke-width="1.2" /><span class="flex-1 text-lg font-light">{{ t('nav.admin') }}</span><ChevronRight :size="18" class="text-subtle" />
      </RouterLink>
    </nav>

    <section class="flex flex-col gap-3">
      <div class="flex items-center justify-between">
        <RouterLink to="/playlists" class="text-[22px] font-bold">{{ t('nav.playlists') }}</RouterLink>
        <button type="button" class="flex h-[34px] items-center gap-1 rounded-full border border-line-strong px-3.5 text-sm" @click="creating = true">
          <Plus :size="16" :stroke-width="1.6" />{{ t('playlists.new') }}
        </button>
      </div>
      <p v-if="!library.playlists.length" class="font-light text-muted">{{ t('playlists.empty') }}</p>
      <RouterLink v-for="p in library.playlists" :key="p.id" :to="{ name: 'playlist', params: { id: p.id } }" class="flex items-center gap-3.5">
        <span class="grid size-[52px] flex-none place-items-center rounded-lg bg-surface"><ListMusic :size="22" :stroke-width="1.3" /></span>
        <span class="flex flex-col">
          <span class="text-[17px]">{{ p.name }}</span>
          <span class="text-sm font-light text-muted">{{ t('common.tracks', p.track_count) }}</span>
        </span>
      </RouterLink>
    </section>

    <BaseModal v-if="creating" :title="t('playlists.new')" @close="creating = false">
      <form class="flex flex-col gap-4" @submit.prevent="create">
        <label class="flex flex-col gap-1.5 text-[13px] text-muted">
          {{ t('playlists.name') }}
          <input v-model="newName" maxlength="200" class="h-12 rounded-full bg-surface px-4 text-base text-ink outline-none focus:ring-2 focus:ring-ink" />
        </label>
        <button type="submit" class="h-12 rounded-full bg-ink text-white disabled:opacity-40" :disabled="!newName.trim()">{{ t('common.create') }}</button>
      </form>
    </BaseModal>
  </div>
</template>
