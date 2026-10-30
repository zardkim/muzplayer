<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { usePlayer } from '../stores/player'
import type { Album } from '../types'
import CoverArt from './CoverArt.vue'
import PlayerIcons from './PlayerIcons.vue'

defineProps<{ albums: Album[]; row?: boolean }>()
const { t } = useI18n()
const player = usePlayer()
</script>

<template>
  <div
    :class="
      row
        ? '-mr-5 flex gap-3 overflow-x-auto pb-2 pr-5 [scrollbar-width:none] md:mr-0 md:pr-0'
        : 'grid grid-cols-2 gap-x-3 gap-y-6 sm:grid-cols-[repeat(auto-fill,minmax(168px,1fr))] sm:gap-x-5'
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
        class="absolute right-2 top-2 grid size-9 place-items-center rounded-full bg-white/80 text-ink backdrop-blur-sm transition-opacity md:opacity-0 md:group-hover:opacity-100 md:focus:opacity-100"
        :aria-label="`${t('common.playAlbum')}: ${a.title}`"
        @click="player.playAlbum(a.id)"
      >
        <PlayerIcons name="play" :size="16" :stroke="1.8" />
      </button>
    </div>
  </div>
</template>
