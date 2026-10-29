<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api'
import { errorMessage } from '../i18n'
import { usePlayer } from '../stores/player'
import { useUi } from '../stores/ui'
import type { ChartDetail } from '../types'
import PageHeader from '../components/PageHeader.vue'
import PlayerIcons from '../components/PlayerIcons.vue'
import TrackList from '../components/TrackList.vue'

const props = defineProps<{ id: string }>()
const { t } = useI18n()
const player = usePlayer()
const ui = useUi()
const chart = ref<ChartDetail | null>(null)
const error = ref('')

onMounted(async () => {
  try {
    chart.value = await api<ChartDetail>(`/charts/${props.id}`)
  } catch (e) {
    error.value = errorMessage(e)
  }
})
</script>

<template>
  <p v-if="error" class="font-light text-muted">{{ error }}</p>
  <div v-else-if="chart" class="flex flex-col gap-5">
    <PageHeader :title="chart.title" :sub="[chart.source, t('common.tracks', chart.tracks.length)].filter(Boolean).join(' · ')" />
    <div class="flex flex-wrap gap-2">
      <button type="button" class="flex h-[38px] items-center gap-1.5 rounded-full bg-ink px-4 text-[15px] text-white" @click="player.playTracks(chart.tracks, 0, { shuffle: false })">
        <PlayerIcons name="play" :size="14" :stroke="2" />{{ t('common.listenAll') }}
      </button>
      <button type="button" class="h-[38px] rounded-full border border-line-strong px-4 text-[15px]" @click="player.playTracks(chart.tracks, 0, { shuffle: true })">{{ t('common.shuffleAll') }}</button>
      <button type="button" class="h-[38px] rounded-full border border-line-strong px-4 text-[15px]" @click="ui.playlistPicker = chart.tracks">{{ t('charts.copyToPlaylist') }}</button>
    </div>
    <TrackList :tracks="chart.tracks" ranked />
  </div>
</template>
