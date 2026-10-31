<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ChevronRight, Folder } from '@lucide/vue'
import { api, query } from '../api'
import { errorMessage } from '../i18n'
import { usePlayer } from '../stores/player'
import type { FolderListing } from '../types'
import CoverArt from '../components/CoverArt.vue'
import LibraryHeader from '../components/LibraryHeader.vue'
import PlayerIcons from '../components/PlayerIcons.vue'
import TrackList from '../components/TrackList.vue'

// The music folder as scanned: subfolders, then the songs directly in this folder.
// Each level is its own history entry (?path=), so back goes up one level.
const { t } = useI18n()
const route = useRoute()
const player = usePlayer()
const path = typeof route.query.path === 'string' ? route.query.path : ''
const listing = ref<FolderListing | null>(null)
const error = ref('')

onMounted(async () => {
  try {
    listing.value = await api<FolderListing>(`/folders${query({ path: path || undefined })}`)
  } catch (e) {
    error.value = errorMessage(e)
  }
})

// root › a › b, each a link to that level
const crumbs = computed(() => {
  const parts = path ? path.split('/') : []
  return parts.map((name, i) => ({ name, path: parts.slice(0, i + 1).join('/') }))
})
const sub = computed(() => {
  const l = listing.value
  if (!l) return undefined
  return [l.folders.length ? t('folders.count', l.folders.length) : '', l.tracks.length ? t('common.tracks', l.tracks.length) : ''].filter(Boolean).join(' · ')
})
</script>

<template>
  <div class="flex flex-col gap-6">
    <LibraryHeader />

    <nav :aria-label="t('folders.path')" class="flex min-w-0 flex-wrap items-center gap-1 text-[15px]">
      <RouterLink :to="{ name: 'folders' }" class="rounded-full px-2 py-1 hover:bg-surface" :class="crumbs.length ? 'font-light text-muted' : 'font-semibold'">{{ t('folders.root') }}</RouterLink>
      <template v-for="(c, i) in crumbs" :key="c.path">
        <ChevronRight :size="16" class="flex-none text-subtle" aria-hidden="true" />
        <RouterLink
          :to="{ name: 'folders', query: { path: c.path } }"
          class="min-w-0 truncate rounded-full px-2 py-1 hover:bg-surface"
          :class="i === crumbs.length - 1 ? 'font-semibold' : 'font-light text-muted'"
          :aria-current="i === crumbs.length - 1 ? 'page' : undefined"
        >{{ c.name }}</RouterLink>
      </template>
      <span v-if="sub" class="ml-auto pl-2 text-[14px] font-light text-muted">{{ sub }}</span>
    </nav>

    <p v-if="error" class="text-danger">{{ error }}</p>
    <p v-else-if="listing && !listing.folders.length && !listing.tracks.length" class="font-light text-muted">{{ t('folders.empty') }}</p>

    <ul v-if="listing?.folders.length" class="grid gap-x-6 sm:grid-cols-2 xl:grid-cols-3">
      <li v-for="f in listing.folders" :key="f.path">
        <RouterLink :to="{ name: 'folders', query: { path: f.path } }" class="group flex min-h-[68px] items-center gap-3.5 border-b border-surface py-2">
          <CoverArt v-if="f.cover" :album-id="f.cover.id" :has-cover="true" :version="f.cover.v" rounded="rounded-lg" class="size-12 flex-none" />
          <span v-else class="grid size-12 flex-none place-items-center rounded-lg bg-surface text-muted"><Folder :size="22" :stroke-width="1.4" /></span>
          <span class="flex min-w-0 flex-1 flex-col">
            <span class="truncate text-[16px] group-hover:underline">{{ f.name }}</span>
            <span class="text-[13px] font-light text-muted">{{ t('common.tracks', f.track_count) }}</span>
          </span>
          <ChevronRight :size="18" class="flex-none text-subtle" />
        </RouterLink>
      </li>
    </ul>

    <section v-if="listing?.tracks.length" class="flex flex-col gap-3">
      <div class="flex flex-wrap gap-2">
        <button type="button" class="flex h-[38px] items-center gap-1.5 rounded-full bg-ink px-4 text-[15px] text-on-ink" @click="player.playTracks(listing.tracks, 0, { shuffle: false })">
          <PlayerIcons name="play" :size="14" :stroke="2" />{{ t('common.listenAll') }}
        </button>
        <button type="button" class="h-[38px] rounded-full border border-line-strong px-4 text-[15px]" @click="player.playTracks(listing.tracks, 0, { shuffle: true })">{{ t('common.shuffleAll') }}</button>
      </div>
      <TrackList :tracks="listing.tracks" show-cover show-album />
    </section>
  </div>
</template>
