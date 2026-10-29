<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ChevronRight } from '@lucide/vue'
import { api, query } from '../api'
import type { Artist, Page } from '../types'
import PageHeader from '../components/PageHeader.vue'

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
  <div class="flex flex-col gap-5">
    <PageHeader :title="t('artists.title')" :sub="t('artists.count', total)" />
    <ul class="grid grid-cols-1 gap-x-8 sm:grid-cols-2 xl:grid-cols-3">
      <li v-for="a in items" :key="a.id">
        <RouterLink :to="{ name: 'artist', params: { id: a.id } }" class="flex min-h-[64px] items-center gap-3.5 border-b border-surface">
          <span class="grid size-11 flex-none place-items-center rounded-full bg-surface font-medium">{{ a.name.slice(0, 1).toUpperCase() }}</span>
          <span class="flex min-w-0 flex-1 flex-col">
            <span class="truncate text-[17px]">{{ a.name }}</span>
            <span class="text-sm font-light text-muted"><template v-if="a.album_count">{{ t('common.albums', a.album_count) }} · </template>{{ t('common.tracks', a.track_count) }}</span>
          </span>
          <ChevronRight :size="18" class="text-subtle" />
        </RouterLink>
      </li>
    </ul>
    <button v-if="items.length < total" type="button" class="mx-auto h-11 rounded-full border border-line-strong px-6 text-[15px]" :disabled="loading" @click="load">
      {{ loading ? t('common.loading') : t('common.loadMore') }}
    </button>
  </div>
</template>
