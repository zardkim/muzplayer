<script setup lang="ts">
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { LIBRARY_ROUTES, type LibraryRoute } from '../router'
import PageHeader from './PageHeader.vue'

// The library's pages (albums, artists, songs, genres, folders) share one header: the title and
// their tabs (the slot sits right of the count line). Each tab is its own route, so lists stay alive and back/forward move between them.
defineProps<{ sub?: string }>()
const { t } = useI18n()
const route = useRoute()

const LABELS: Record<LibraryRoute, string> = {
  albums: 'nav.albums',
  artists: 'nav.artists',
  tracks: 'nav.songs',
  genres: 'nav.genres',
  folders: 'nav.folders',
}
</script>

<template>
  <div class="flex flex-col gap-3">
    <PageHeader :title="t('nav.libraryMenu')" />
    <nav :aria-label="t('nav.libraryMenu')" class="-mx-5 flex gap-1 overflow-x-auto border-b border-line px-5 [scrollbar-width:none] md:mx-0 md:px-0">
      <RouterLink
        v-for="name in LIBRARY_ROUTES"
        :key="name"
        :to="{ name }"
        class="-mb-px flex h-11 flex-none items-center border-b-2 px-3 text-[16px] transition-colors"
        :class="route.name === name ? 'border-ink font-semibold' : 'border-transparent font-light text-muted hover:text-ink'"
        :aria-current="route.name === name ? 'page' : undefined"
      >
        {{ t(LABELS[name]) }}
      </RouterLink>
    </nav>
    <!-- on a narrow screen the controls go to their own line rather than squeeze the count -->
    <div v-if="sub || $slots.default" class="flex min-h-8 flex-wrap items-center justify-between gap-x-3 gap-y-2">
      <p class="whitespace-nowrap text-[15px] font-light text-muted">{{ sub }}</p>
      <div v-if="$slots.default" class="ml-auto flex-none"><slot /></div>
    </div>
  </div>
</template>
