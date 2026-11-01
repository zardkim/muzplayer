<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { Square } from '@lucide/vue'
import { api } from '../api'
import { errorMessage } from '../i18n'
import { usePlayer } from '../stores/player'
import { useUi } from '../stores/ui'
import type { RadioStation } from '../types'
import PageHeader from '../components/PageHeader.vue'
import PlayerIcons from '../components/PlayerIcons.vue'
import StationBadge from '../components/StationBadge.vue'

// Korean radio, live (backend radio.py relays each station). Stations by region; the region picked
// last is remembered.
const { t } = useI18n()
const player = usePlayer()
const ui = useUi()
const regions = ref<string[]>([])
const stations = ref<RadioStation[]>([])
const error = ref('')
const region = computed({
  get: () => ui.views.radio || 'seoul',
  set: (v: string) => (ui.views = { ...ui.views, radio: v }),
})
const shown = computed(() => stations.value.filter((s) => s.regions.includes(region.value)))
const live = computed(() => (player.mode === 'live' ? player.station : null))

onMounted(async () => {
  try {
    const r = await api<{ regions: string[]; stations: RadioStation[] }>('/radio/stations')
    regions.value = r.regions
    stations.value = r.stations
  } catch (e) {
    error.value = errorMessage(e)
  }
})

function tune(s: RadioStation) {
  if (live.value?.id === s.id) player.toggle()
  else player.playStation(s)
}
</script>

<template>
  <div class="flex flex-col gap-6">
    <PageHeader :title="t('radio.title')" :sub="stations.length ? t('radio.count', { n: shown.length }) : ''" />

    <!-- what is on now -->
    <div v-if="live" class="flex items-center gap-3.5 rounded-2xl bg-surface p-3.5">
      <StationBadge :stn="live.stn" :logo="live.logo" class="size-12 text-[15px]" />
      <span class="flex min-w-0 flex-1 flex-col">
        <span class="flex items-center gap-2"><span class="rounded bg-danger px-1.5 text-[11px] font-bold leading-[18px] text-white">LIVE</span><span class="truncate text-[17px] font-medium">{{ live.name }}</span></span>
        <span class="text-[13px] font-light text-muted">{{ player.playing ? t('radio.onAir') : t('radio.paused') }}</span>
      </span>
      <button type="button" class="grid size-11 place-items-center rounded-full bg-ink text-on-ink" :aria-label="player.playing ? t('player.pause') : t('player.play')" @click="player.toggle()">
        <PlayerIcons :name="player.playing ? 'pause' : 'play'" :size="20" :stroke="1.8" />
      </button>
      <button type="button" class="grid size-11 place-items-center rounded-full border border-line-strong" :aria-label="t('radio.stop')" :title="t('radio.stop')" @click="player.stopStation()">
        <Square :size="16" :stroke-width="2" />
      </button>
    </div>

    <div class="-mr-5 flex gap-2 overflow-x-auto pr-5 [scrollbar-width:none] md:mr-0 md:flex-wrap md:pr-0">
      <button
        v-for="r in regions"
        :key="r"
        type="button"
        class="h-[38px] flex-none rounded-full border px-4 text-[15px]"
        :class="region === r ? 'border-ink bg-ink text-on-ink' : 'border-line-strong bg-bg'"
        :aria-pressed="region === r"
        @click="region = r"
      >
        {{ t(`radio.region_${r}`) }}
      </button>
    </div>

    <p v-if="error" class="font-light text-muted">{{ error }}</p>
    <ul class="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
      <li v-for="s in shown" :key="s.id">
        <button
          type="button"
          class="flex w-full items-center gap-3.5 rounded-2xl p-2.5 text-left transition-colors"
          :class="live?.id === s.id ? 'bg-accent-soft' : 'hover:bg-surface'"
          :aria-pressed="live?.id === s.id"
          @click="tune(s)"
        >
          <StationBadge :stn="s.stn" :logo="s.logo" class="size-11 text-[13px]" />
          <span class="min-w-0 flex-1 truncate text-[16px]" :class="live?.id === s.id ? 'font-medium text-accent' : ''">{{ s.name }}</span>
          <PlayerIcons v-if="live?.id === s.id" :name="player.playing ? 'pause' : 'play'" :size="18" :stroke="1.8" class="mr-1.5 flex-none text-accent" />
        </button>
      </li>
    </ul>
    <p class="text-[12px] font-light text-subtle">{{ t('radio.source') }}</p>
  </div>
</template>
