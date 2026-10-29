<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api'
import type { Track } from '../types'
import PageHeader from '../components/PageHeader.vue'
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
  <div class="flex flex-col gap-5">
    <PageHeader :title="t('history.title')" />
    <p v-if="loaded && !items.length" class="font-light text-muted">{{ t('history.empty') }}</p>
    <TrackList :tracks="items" />
  </div>
</template>
