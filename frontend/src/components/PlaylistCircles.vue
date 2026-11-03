<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ListMusic, Zap } from '@lucide/vue'
import { api, coverUrl } from '../api'
import { errorMessage } from '../i18n'
import { useLibrary } from '../stores/library'
import { usePlayer } from '../stores/player'
import { useUi } from '../stores/ui'
import type { Playlist, PlaylistDetail, Track } from '../types'
import PlayerIcons from './PlayerIcons.vue'
import RowArrows from './RowArrows.vue'

// Home: round cards that play at a tap — this person's playlists (random 100 is with the stations).
// The name under a playlist opens it.
const { t } = useI18n()
const library = useLibrary()
const player = usePlayer()
const ui = useUi()
const row = ref<HTMLElement | null>(null)
const busy = ref<string | null>(null)

async function play(key: string, load: () => Promise<Track[]>) {
  if (busy.value) return
  busy.value = key
  try {
    const tracks = await load()
    if (!tracks.length) return ui.notify(t('home.emptyList'), true)
    player.playTracks(tracks, 0, { shuffle: false })
  } catch (e) {
    ui.notify(errorMessage(e), true)
  } finally {
    busy.value = null
  }
}
const playlist = (p: Playlist) => play(`p${p.id}`, async () => (await api<PlaylistDetail>(`/playlists/${p.id}`)).entries.map((e) => e.track))
</script>

<template>
  <div class="relative">
    <div ref="row" class="-mr-5 flex gap-4 overflow-x-auto pb-1 pr-5 [scrollbar-width:none] md:mr-0 md:pr-0">
      <div v-for="p in library.playlists" :key="p.id" class="flex w-[104px] flex-none flex-col items-center gap-2 sm:w-28">
        <button type="button" class="group relative aspect-square w-full overflow-hidden rounded-full bg-surface shadow-md" :aria-label="`${t('common.play')}: ${p.name}`" @click="playlist(p)">
          <img v-if="p.cover" :src="coverUrl(p.cover.id, 'thumb', p.cover.v)" alt="" loading="lazy" class="h-full w-full object-cover" />
          <span v-else class="grid h-full w-full place-items-center bg-[linear-gradient(135deg,#2B2D42,#5C4B8A)] text-white/85">
            <Zap v-if="p.kind === 'smart'" :size="30" :stroke-width="1.3" :class="busy === `p${p.id}` ? 'animate-pulse' : ''" /><ListMusic v-else :size="30" :stroke-width="1.3" :class="busy === `p${p.id}` ? 'animate-pulse' : ''" />
          </span>
          <!-- over a cover only (an icon card is plain enough to read as a button) -->
          <span v-if="p.cover" class="absolute inset-0 grid place-items-center bg-black/25 text-white transition-opacity md:opacity-0 md:group-hover:opacity-100" :class="busy === `p${p.id}` ? 'opacity-100' : ''">
            <PlayerIcons name="play" :size="26" :stroke="1.8" />
          </span>
        </button>
        <RouterLink :to="{ name: 'playlist', params: { id: p.id } }" class="w-full truncate text-center text-[14px]">{{ p.name }}</RouterLink>
      </div>
    </div>
    <RowArrows v-if="row" :row="row" />
  </div>
</template>
