<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api'
import { usePlayer } from '../stores/player'
import type { Chart, ChartDetail } from '../types'
import CoverArt from './CoverArt.vue'
import PlayerIcons from './PlayerIcons.vue'
import RowArrows from './RowArrows.vue'

defineProps<{ charts: Chart[]; row?: boolean }>()
const { t } = useI18n()
const player = usePlayer()
const list = ref<HTMLElement | null>(null)

async function play(id: number) {
  const chart = await api<ChartDetail>(`/charts/${id}`)
  player.playTracks(chart.tracks, 0, { shuffle: false })
}
</script>

<template>
  <div :class="row ? 'relative' : 'contents'">
    <div
      ref="list"
      :class="
        row
          ? '-mr-5 flex gap-3 overflow-x-auto pb-2 pr-5 [scrollbar-width:none] md:mr-0 md:pr-0'
          : 'grid grid-cols-2 gap-x-3 gap-y-6 sm:grid-cols-[repeat(auto-fill,minmax(168px,1fr))] sm:gap-x-5'
      "
    >
      <div v-for="c in charts" :key="c.id" class="group relative flex min-w-0 flex-col gap-2" :class="row ? 'w-[140px] flex-none sm:w-40' : ''">
        <RouterLink :to="{ name: 'chart', params: { id: c.id } }" class="flex flex-col gap-2">
          <CoverArt :album-id="c.cover_albums[0]?.id ?? null" :has-cover="c.cover_albums.length > 0" :version="c.cover_albums[0]?.v">
            <span v-if="c.source" class="absolute left-2 top-2 rounded-full bg-ink/80 px-2 py-0.5 text-[12px] font-medium text-on-ink">{{ c.source }}</span>
          </CoverArt>
          <span class="flex min-w-0 flex-col">
            <span class="truncate text-base">{{ c.title }}</span>
            <span class="truncate text-sm font-light text-muted">{{ t('common.tracks', c.track_count) }}</span>
          </span>
        </RouterLink>
        <button
          type="button"
          class="absolute right-2 top-2 grid size-9 place-items-center rounded-full bg-bg/80 text-ink backdrop-blur-sm transition-opacity md:opacity-0 md:group-hover:opacity-100 md:focus:opacity-100"
          :aria-label="`${t('common.play')}: ${c.source} ${c.title}`"
          @click="play(c.id)"
        >
          <PlayerIcons name="play" :size="16" :stroke="1.8" />
        </button>
      </div>
    </div>
    <RowArrows v-if="row && list" :row="list" />
  </div>
</template>
