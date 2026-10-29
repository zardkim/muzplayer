<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { api, query } from '../api'
import type { Album, Page } from '../types'
import AlbumGrid from '../components/AlbumGrid.vue'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const sort = computed(() => (typeof route.query.sort === 'string' ? route.query.sort : 'recent'))
const items = ref<Album[]>([])
const total = ref(0)
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    const page = await api<Page<Album>>(`/albums${query({ sort: sort.value, limit: 120, offset: items.value.length })}`)
    items.value.push(...page.items)
    total.value = page.total
  } finally {
    loading.value = false
  }
}
onMounted(load)

const sorts = [
  { key: 'recent', label: 'albums.sortRecent' },
  { key: 'title', label: 'albums.sortTitle' },
  { key: 'artist', label: 'albums.sortArtist' },
  { key: 'year', label: 'albums.sortYear' },
]
</script>

<template>
  <div class="flex flex-col gap-7">
    <div class="flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 class="text-[32px] font-bold tracking-tight">{{ t('albums.title') }}</h1>
        <p class="mt-1 text-sm text-muted">{{ t('albums.count', total) }}</p>
      </div>
      <div class="flex flex-wrap gap-1.5">
        <button
          v-for="s in sorts"
          :key="s.key"
          type="button"
          class="h-9 rounded-full px-3.5 text-[13px]"
          :class="sort === s.key ? 'bg-ink font-semibold text-bg' : 'bg-surface-2 text-ink'"
          @click="router.replace({ query: { sort: s.key } })"
        >
          {{ t(s.label) }}
        </button>
      </div>
    </div>
    <AlbumGrid :albums="items" />
    <button v-if="items.length < total" type="button" class="mx-auto h-11 rounded-full bg-surface-2 px-6 text-sm" :disabled="loading" @click="load">
      {{ loading ? t('common.loading') : t('common.loadMore') }}
    </button>
  </div>
</template>
