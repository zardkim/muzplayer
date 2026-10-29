<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api'
import type { Track } from '../types'
import TrackList from '../components/TrackList.vue'

const { t } = useI18n()
const items = ref<Track[]>([])
const loaded = ref(false)
onMounted(async () => {
  items.value = (await api<{ items: Track[] }>('/history?limit=200')).items
  loaded.value = true
})
</script>

<template>
  <div class="flex flex-col gap-6">
    <h1 class="text-[32px] font-bold tracking-tight">{{ t('history.title') }}</h1>
    <p v-if="loaded && !items.length" class="text-muted">{{ t('history.empty') }}</p>
    <TrackList :tracks="items" />
  </div>
</template>
