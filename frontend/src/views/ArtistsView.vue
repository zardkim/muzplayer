<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, query } from '../api'
import type { Artist, Page } from '../types'

const { t } = useI18n()
const items = ref<Artist[]>([])
const total = ref(0)
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    const page = await api<Page<Artist>>(`/artists${query({ limit: 500, offset: items.value.length })}`)
    items.value.push(...page.items)
    total.value = page.total
  } finally {
    loading.value = false
  }
}
onMounted(load)
</script>

<template>
  <div class="flex flex-col gap-6">
    <div>
      <h1 class="text-[32px] font-bold tracking-tight">{{ t('artists.title') }}</h1>
      <p class="mt-1 text-sm text-muted">{{ t('artists.count', total) }}</p>
    </div>
    <ul class="grid grid-cols-1 gap-x-6 sm:grid-cols-2 xl:grid-cols-3">
      <li v-for="a in items" :key="a.id">
        <RouterLink :to="{ name: 'artist', params: { id: a.id } }" class="flex min-h-[60px] items-center gap-3.5 rounded-xl px-2 hover:bg-surface">
          <span class="grid size-11 flex-none place-items-center rounded-full bg-surface-2 font-semibold text-muted">{{ a.name.slice(0, 1).toUpperCase() }}</span>
          <span class="flex min-w-0 flex-col">
            <span class="truncate text-[15px] font-semibold">{{ a.name }}</span>
            <span class="text-[13px] text-muted">
              <template v-if="a.album_count">{{ t('common.albums', a.album_count) }} · </template>{{ t('common.tracks', a.track_count) }}
            </span>
          </span>
        </RouterLink>
      </li>
    </ul>
    <button v-if="items.length < total" type="button" class="mx-auto h-11 rounded-full bg-surface-2 px-6 text-sm" :disabled="loading" @click="load">
      {{ loading ? t('common.loading') : t('common.loadMore') }}
    </button>
  </div>
</template>
