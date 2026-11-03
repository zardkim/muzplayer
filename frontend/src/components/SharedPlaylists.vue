<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ListMusic } from '@lucide/vue'
import { api, coverUrl } from '../api'
import type { Playlist } from '../types'
import SectionTitle from './SectionTitle.vue'

// The shared playlists (made from charts and themes, for everyone): a row of cards on the charts &
// themes page and at home. Nothing is shown while there are none.
const { t } = useI18n()
const items = ref<Playlist[]>([])
onMounted(async () => {
  items.value = (await api<{ items: Playlist[] }>('/playlists/shared').catch(() => ({ items: [] }))).items
})
</script>

<template>
  <section v-if="items.length" class="flex flex-col gap-3.5">
    <SectionTitle :title="t('shared.title')" />
    <ul class="-mr-5 flex gap-3 overflow-x-auto pb-2 pr-5 [scrollbar-width:none] md:mr-0 md:pr-0">
      <li v-for="p in items" :key="p.id" class="w-[140px] flex-none sm:w-40">
        <RouterLink :to="{ name: 'playlist', params: { id: p.id } }" class="group flex flex-col gap-2">
          <span class="relative block aspect-square overflow-hidden rounded-xl bg-surface shadow-sm">
            <img v-if="p.cover" :src="coverUrl(p.cover.id, 'thumb', p.cover.v)" alt="" loading="lazy" class="h-full w-full object-cover transition-transform duration-300 group-hover:scale-[1.03]" />
            <span v-else class="grid h-full w-full place-items-center bg-[linear-gradient(135deg,#2B2D42,#5C4B8A)] text-white/85"><ListMusic :size="34" :stroke-width="1.3" /></span>
          </span>
          <span class="flex min-w-0 flex-col">
            <span class="truncate text-[15px] font-medium">{{ p.name }}</span>
            <span class="truncate text-[13px] font-light text-muted">{{ t('common.tracks', p.track_count ?? 0) }}</span>
          </span>
        </RouterLink>
      </li>
    </ul>
  </section>
</template>
