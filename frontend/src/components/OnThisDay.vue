<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, query } from '../api'
import type { Album } from '../types'
import CoverArt from './CoverArt.vue'

// "On this day": albums released on today's date in earlier years (needs whole release dates in
// the tags). Shows nothing when there are none.
const { t } = useI18n()
const albums = ref<Album[]>([])
const now = new Date()
const day = `${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`

onMounted(async () => {
  albums.value = (await api<{ items: Album[] }>(`/albums/on-this-day${query({ day })}`).catch(() => ({ items: [] }))).items
})
const yearsAgo = (a: Album) => now.getFullYear() - Number(a.release_date!.slice(0, 4))
</script>

<template>
  <section v-if="albums.length" class="flex flex-col gap-3">
    <h2 class="text-[22px] font-bold">{{ t('home.onThisDay') }}</h2>
    <div class="-mr-5 flex snap-x gap-3 overflow-x-auto pr-5 [scrollbar-width:none]">
      <RouterLink
        v-for="a in albums"
        :key="a.id"
        :to="{ name: 'album', params: { id: a.id } }"
        class="flex w-[min(86%,420px)] flex-none snap-start items-center gap-4 rounded-2xl bg-surface p-4 hover:bg-surface-2"
      >
        <CoverArt :album-id="a.id" :has-cover="a.has_cover" :version="a.cover_v" rounded="rounded-lg" class="size-24 flex-none shadow-sm" />
        <span class="flex min-w-0 flex-col gap-0.5">
          <span class="text-[19px] font-bold">{{ t('home.yearsAgo', yearsAgo(a)) }}</span>
          <span class="truncate text-[16px]">{{ a.title || t('common.unknownAlbum') }}</span>
          <span class="truncate text-[14px] font-light text-muted">{{ a.artist || t('common.unknownArtist') }}</span>
          <span class="font-display text-[14px] font-light text-muted">{{ a.release_date?.slice(0, 4) }}</span>
        </span>
      </RouterLink>
    </div>
  </section>
</template>
