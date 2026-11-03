<script setup lang="ts">
import { ref, type Component } from 'vue'
import { useI18n } from 'vue-i18n'
import { CalendarRange, Dices, Disc3, Gem, History, MicVocal, Radio, Shuffle, Tags } from '@lucide/vue'
import { api } from '../api'
import { errorMessage } from '../i18n'
import { usePlayer } from '../stores/player'
import { useUi } from '../stores/ui'
import type { Track } from '../types'
import StationPicker from './StationPicker.vue'

// Home → stations: a tile for each way of playing on and on (backend stations.py), and random 100.
// Some ask first what to play from (an artist, an album, a genre, a decade).
type Pick = 'artist' | 'album' | 'genre' | 'decade'
type Key = 'random' | 'library' | 'hidden' | 'timetravel' | 'randomalbum' | Pick
const TILES: { key: Key; icon: Component; tint: string; pick?: true }[] = [
  { key: 'random', icon: Shuffle, tint: '217 59 34' },
  { key: 'artist', icon: MicVocal, tint: '190 80 110', pick: true },
  { key: 'album', icon: Disc3, tint: '96 150 90', pick: true },
  { key: 'library', icon: Radio, tint: '80 130 170' },
  { key: 'hidden', icon: Gem, tint: '150 100 180' },
  { key: 'timetravel', icon: History, tint: '180 140 70' },
  { key: 'randomalbum', icon: Dices, tint: '110 120 170' },
  { key: 'genre', icon: Tags, tint: '70 150 150', pick: true },
  { key: 'decade', icon: CalendarRange, tint: '160 110 140', pick: true },
]
const { t } = useI18n()
const player = usePlayer()
const ui = useUi()
const busy = ref<Key | null>(null)
const picking = ref<Pick | null>(null)

async function run(key: Key, start: () => Promise<boolean>) {
  if (busy.value) return
  busy.value = key
  try {
    if (!(await start())) ui.notify(t('home.emptyList'), true)
  } catch (e) {
    ui.notify(errorMessage(e), true)
  } finally {
    busy.value = null
  }
}
function tap(key: Key, pick?: true) {
  if (pick) return (picking.value = key as Pick)
  if (key === 'random') {
    return run(key, async () => {
      const r = await api<{ tracks: Track[] }>('/mixes/random')
      if (!r.tracks.length) return false
      player.playTracks(r.tracks, 0, { shuffle: false })
      return true
    })
  }
  return run(key, () => player.startStation(key))
}
function picked(params: Record<string, number>) {
  const key = picking.value!
  picking.value = null
  void run(key, () => player.startStation(key, params))
}
</script>

<template>
  <section class="flex flex-col gap-3">
    <h2 class="text-[22px] font-bold">{{ t('stations.title') }}</h2>
    <ul class="grid grid-cols-3 gap-2.5 sm:grid-cols-[repeat(auto-fill,minmax(120px,1fr))] sm:gap-3">
      <li v-for="tile in TILES" :key="tile.key">
        <button
          type="button"
          class="flex aspect-square w-full flex-col items-center justify-center gap-2 rounded-xl border border-line px-2 text-center transition-transform active:scale-95"
          :style="{ background: `linear-gradient(160deg, rgb(${tile.tint} / 0.22), rgb(${tile.tint} / 0.1))` }"
          @click="tap(tile.key, tile.pick)"
        >
          <component :is="tile.icon" :size="28" :stroke-width="1.6" :class="busy === tile.key ? 'animate-pulse' : ''" aria-hidden="true" />
          <span class="text-[14px] font-semibold leading-tight break-keep">{{ t(`stations.${tile.key}`) }}</span>
        </button>
      </li>
    </ul>
    <StationPicker v-if="picking" :kind="picking" @close="picking = null" @pick="picked" />
  </section>
</template>
