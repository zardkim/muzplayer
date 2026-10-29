<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api'
import type { Genre } from '../types'

const { t } = useI18n()
const items = ref<Genre[]>([])
const loaded = ref(false)
onMounted(async () => {
  items.value = (await api<{ items: Genre[] }>('/genres')).items
  loaded.value = true
})
</script>

<template>
  <div class="flex flex-col gap-6">
    <h1 class="text-[32px] font-bold tracking-tight">{{ t('genres.title') }}</h1>
    <p v-if="loaded && !items.length" class="text-muted">{{ t('genres.empty') }}</p>
    <div class="flex flex-wrap gap-2.5">
      <RouterLink
        v-for="g in items"
        :key="g.id"
        :to="{ name: 'tracks', query: { genre: g.id } }"
        class="flex items-center gap-2 rounded-full bg-surface-2 px-4 py-2.5 text-[15px] hover:bg-line"
      >
        {{ g.name }} <span class="font-display text-xs text-muted">{{ g.track_count }}</span>
      </RouterLink>
    </div>
  </div>
</template>
