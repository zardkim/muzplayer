<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api'
import type { Genre } from '../types'
import PageHeader from '../components/PageHeader.vue'

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
    <PageHeader :title="t('genres.title')" />
    <p v-if="loaded && !items.length" class="font-light text-muted">{{ t('genres.empty') }}</p>
    <div class="flex flex-wrap gap-2.5">
      <RouterLink
        v-for="g in items"
        :key="g.id"
        :to="{ name: 'tracks', query: { genre: g.id } }"
        class="flex h-11 items-center gap-2 rounded-full border border-line-strong px-[18px] text-base font-light hover:border-ink"
      >
        #{{ g.name }} <span class="font-display text-xs text-muted">{{ g.track_count }}</span>
      </RouterLink>
    </div>
  </div>
</template>
