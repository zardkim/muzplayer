<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { api, query } from '../api'
import type { Album, Page } from '../types'
import AlbumGrid from '../components/AlbumGrid.vue'
import PageHeader from '../components/PageHeader.vue'

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
  <div class="flex flex-col gap-6">
    <PageHeader :title="t('albums.title')" :sub="t('albums.count', total)" />
    <div class="-mr-5 flex gap-2 overflow-x-auto pr-5 [scrollbar-width:none]">
      <button
        v-for="s in sorts"
        :key="s.key"
        type="button"
        class="h-[38px] flex-none rounded-full border px-4 text-[15px]"
        :class="sort === s.key ? 'border-ink bg-ink text-white' : 'border-line-strong bg-bg'"
        @click="router.replace({ query: { sort: s.key } })"
      >
        {{ t(s.label) }}
      </button>
    </div>
    <AlbumGrid :albums="items" />
    <button v-if="items.length < total" type="button" class="mx-auto h-11 rounded-full border border-line-strong px-6 text-[15px]" :disabled="loading" @click="load">
      {{ loading ? t('common.loading') : t('common.loadMore') }}
    </button>
  </div>
</template>
