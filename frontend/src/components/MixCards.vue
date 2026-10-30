<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { Shuffle } from '@lucide/vue'
import { coverUrl } from '../api'
import type { Mix } from '../types'

// A row of mix cards: up to four covers in a grid over a soft backdrop, name and song count below.
defineProps<{ mixes: Mix[] }>()
const { t } = useI18n()
</script>

<template>
  <div class="-mr-5 flex gap-3 overflow-x-auto pb-2 pr-5 [scrollbar-width:none] md:mr-0 md:pr-0">
    <RouterLink
      v-for="m in mixes"
      :key="m.key"
      :to="{ name: 'mix', params: { mixKey: m.key } }"
      class="flex w-[140px] flex-none flex-col gap-2 sm:w-40"
    >
      <span class="relative grid aspect-square grid-cols-2 overflow-hidden rounded-xl bg-[linear-gradient(135deg,#2B2D42,#5C4B8A)]">
        <template v-if="m.cover_albums.length >= 4">
          <img v-for="c in m.cover_albums" :key="c.id" :src="coverUrl(c.id, 'thumb', c.v)" alt="" loading="lazy" class="aspect-square h-full w-full object-cover" />
        </template>
        <img v-else-if="m.cover_albums.length" :src="coverUrl(m.cover_albums[0].id, 'thumb', m.cover_albums[0].v)" alt="" loading="lazy" class="col-span-2 h-full w-full object-cover" />
        <span v-else class="col-span-2 grid place-items-center text-white/80"><Shuffle :size="34" :stroke-width="1.2" /></span>
        <span class="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/70 to-transparent px-2.5 pb-2 pt-6 text-[15px] font-bold leading-tight text-white">
          {{ t(`mixes.names.${m.key}`) }}
        </span>
      </span>
      <span class="truncate text-sm font-light text-muted">{{ t('common.tracks', m.track_count) }}</span>
    </RouterLink>
  </div>
</template>
