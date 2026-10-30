<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { usePlayer } from '../stores/player'
import type { Album, ViewMode } from '../types'
import CoverArt from './CoverArt.vue'
import PlayerIcons from './PlayerIcons.vue'

// mode: cover (big artwork, the default), grid (small and dense) or list (rows); row: one scrolling row
withDefaults(defineProps<{ albums: Album[]; row?: boolean; mode?: ViewMode }>(), { mode: 'cover' })
const { t } = useI18n()
const player = usePlayer()
</script>

<template>
  <ul v-if="mode === 'list' && !row" class="flex flex-col">
    <li v-for="a in albums" :key="a.id" class="group flex items-center gap-3.5 border-b border-surface py-2">
      <RouterLink :to="{ name: 'album', params: { id: a.id } }" class="flex min-w-0 flex-1 items-center gap-3.5">
        <CoverArt :album-id="a.id" :has-cover="a.has_cover" :version="a.cover_v" rounded="rounded-md" class="size-14 flex-none" />
        <span class="flex min-w-0 flex-1 flex-col">
          <span class="truncate text-[16px]">{{ a.title || t('common.unknownAlbum') }}</span>
          <span class="flex min-w-0 items-center gap-1.5 text-sm font-light text-muted">
            <span v-if="a.kind === 'unofficial' || a.kind === 'compilation'" class="flex-none rounded border border-line-strong px-1 text-[11px] leading-[18px]">{{ t(`albums.kind_${a.kind}`) }}</span>
            <span class="truncate">{{ a.artist || t('common.unknownArtist') }}</span>
          </span>
        </span>
        <span class="hidden w-14 text-right font-display text-sm text-muted sm:block">{{ a.year || '' }}</span>
        <span class="hidden w-20 text-right text-sm font-light text-muted md:block">{{ t('common.tracks', a.track_count ?? 0) }}</span>
      </RouterLink>
      <button
        type="button"
        class="grid size-10 flex-none place-items-center rounded-full hover:bg-surface md:opacity-0 md:group-hover:opacity-100 md:focus:opacity-100"
        :aria-label="`${t('common.playAlbum')}: ${a.title}`"
        @click="player.playAlbum(a.id)"
      >
        <PlayerIcons name="play" :size="16" :stroke="1.8" />
      </button>
    </li>
  </ul>
  <div
    v-else
    :class="
      row
        ? '-mr-5 flex gap-3 overflow-x-auto pb-2 pr-5 [scrollbar-width:none] md:mr-0 md:pr-0'
        : mode === 'grid'
          ? 'grid grid-cols-3 gap-x-2.5 gap-y-4 sm:grid-cols-[repeat(auto-fill,minmax(128px,1fr))] sm:gap-x-4'
          : 'grid grid-cols-2 gap-x-3 gap-y-6 sm:grid-cols-[repeat(auto-fill,minmax(190px,1fr))] sm:gap-x-5'
    "
  >
    <div v-for="a in albums" :key="a.id" class="group relative flex min-w-0 flex-col gap-2" :class="row ? 'w-[140px] flex-none sm:w-40' : ''">
      <RouterLink :to="{ name: 'album', params: { id: a.id } }" class="flex flex-col gap-2">
        <CoverArt :album-id="a.id" :has-cover="a.has_cover" :version="a.cover_v" />
        <span class="flex min-w-0 flex-col">
          <span class="truncate text-base">{{ a.title || t('common.unknownAlbum') }}</span>
          <span class="flex min-w-0 items-center gap-1.5 text-sm font-light text-muted">
            <span v-if="a.kind === 'unofficial' || a.kind === 'compilation'" class="flex-none rounded border border-line-strong px-1 text-[11px] leading-[18px]">{{ t(`albums.kind_${a.kind}`) }}</span>
            <span class="truncate">{{ a.artist || t('common.unknownArtist') }}</span>
          </span>
        </span>
      </RouterLink>
      <button
        type="button"
        class="absolute right-2 top-2 place-items-center rounded-full bg-white/80 text-ink backdrop-blur-sm transition-opacity md:opacity-0 md:group-hover:opacity-100 md:focus:opacity-100"
        :class="mode === 'grid' && !row ? 'hidden size-8 md:grid' : 'grid size-9'"
        :aria-label="`${t('common.playAlbum')}: ${a.title}`"
        @click="player.playAlbum(a.id)"
      >
        <PlayerIcons name="play" :size="16" :stroke="1.8" />
      </button>
    </div>
  </div>
</template>
