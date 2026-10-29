<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { Play, Shuffle } from '@lucide/vue'
import { api } from '../api'
import { usePlayer } from '../stores/player'
import type { Track } from '../types'
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
  <div class="flex flex-col gap-6">
    <div class="flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 class="text-[32px] font-bold tracking-tight">{{ t('favorites.title') }}</h1>
        <p class="mt-1 text-sm text-muted">{{ t('common.tracks', items.length) }}</p>
      </div>
      <div v-if="items.length" class="flex gap-2">
        <button type="button" class="flex h-11 items-center gap-2 rounded-full bg-accent px-5 font-semibold text-bg" @click="player.playTracks(items, 0, { shuffle: false })">
          <Play :size="18" fill="currentColor" />{{ t('common.playAll') }}
        </button>
        <button type="button" class="flex h-11 items-center gap-2 rounded-full border border-line-strong px-5 font-semibold" @click="player.playTracks(items, 0, { shuffle: true })">
          <Shuffle :size="18" />{{ t('common.shuffleAll') }}
        </button>
      </div>
    </div>
    <p v-if="loaded && !items.length" class="text-muted">{{ t('favorites.empty') }}</p>
    <TrackList :tracks="items" />
  </div>
</template>
