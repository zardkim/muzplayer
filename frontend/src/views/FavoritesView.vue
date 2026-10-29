<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api'
import { usePlayer } from '../stores/player'
import type { Track } from '../types'
import PageHeader from '../components/PageHeader.vue'
import PlayerIcons from '../components/PlayerIcons.vue'
import TrackList from '../components/TrackList.vue'

const { t } = useI18n()
const player = usePlayer()
const items = ref<Track[]>([])
const loaded = ref(false)
onMounted(async () => {
  items.value = (await api<{ items: Track[] }>('/favorites')).items
  loaded.value = true
})
</script>

<template>
  <div class="flex flex-col gap-5">
    <PageHeader :title="t('favorites.title')" :sub="t('common.tracks', items.length)" />
    <div v-if="items.length" class="flex gap-2">
      <button type="button" class="flex h-[38px] items-center gap-1.5 rounded-full bg-ink px-4 text-[15px] text-white" @click="player.playTracks(items, 0, { shuffle: false })">
        <PlayerIcons name="play" :size="14" :stroke="2" />{{ t('common.listenAll') }}
      </button>
      <button type="button" class="h-[38px] rounded-full border border-line-strong px-4 text-[15px]" @click="player.playTracks(items, 0, { shuffle: true })">{{ t('common.shuffleAll') }}</button>
    </div>
    <p v-if="loaded && !items.length" class="font-light text-muted">{{ t('favorites.empty') }}</p>
    <TrackList :tracks="items" />
  </div>
</template>
