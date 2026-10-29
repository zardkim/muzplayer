<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { Album } from '../types'
import CoverArt from './CoverArt.vue'

defineProps<{ albums: Album[]; row?: boolean }>()
const { t } = useI18n()
</script>

<template>
  <div
    :class="
      row
        ? 'flex gap-4 overflow-x-auto pb-2 [scrollbar-width:none]'
        : 'grid grid-cols-[repeat(auto-fill,minmax(150px,1fr))] gap-x-6 gap-y-7 sm:grid-cols-[repeat(auto-fill,minmax(168px,1fr))]'
    "
  >
    <RouterLink
      v-for="a in albums"
      :key="a.id"
      :to="{ name: 'album', params: { id: a.id } }"
      class="group flex min-w-0 flex-col gap-2.5"
      :class="row ? 'w-[132px] flex-none sm:w-40' : ''"
    >
      <CoverArt :album-id="a.id" :has-cover="a.has_cover" class="transition-transform group-hover:scale-[1.02]" />
      <div class="flex min-w-0 flex-col">
        <span class="truncate text-[15px] font-semibold group-hover:text-accent-strong">{{ a.title || t('common.unknownAlbum') }}</span>
        <span class="truncate text-[13px] text-muted">
          {{ a.artist || t('common.unknownArtist') }}<template v-if="a.year"> · {{ a.year }}</template>
        </span>
      </div>
    </RouterLink>
  </div>
</template>
