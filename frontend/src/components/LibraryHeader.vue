<script setup lang="ts">
import { useRoute } from 'vue-router'
import { type Component } from 'vue'
import { useI18n } from 'vue-i18n'
import { Disc3, Folder, MicVocal, Music2, Tags } from '@lucide/vue'
import { LIBRARY_ROUTES, type LibraryRoute } from '../router'
import PageHeader from './PageHeader.vue'
import SearchField from './SearchField.vue'

// The library's pages (albums, artists, songs, genres, folders) share one header: the title and
// their tabs (the slot sits right of the count line), and the page's search box when it binds one.
// Each tab is its own route, so lists stay alive and back/forward move between them.
defineProps<{ sub?: string; searchLabel?: string }>()
const search = defineModel<string>('search')
const { t } = useI18n()
const route = useRoute()

const LABELS: Record<LibraryRoute, string> = {
  albums: 'nav.albums',
  artists: 'nav.artists',
  tracks: 'nav.songs',
  genres: 'nav.genres',
  folders: 'nav.folders',
}
const ICONS: Record<LibraryRoute, Component> = { albums: Disc3, artists: MicVocal, tracks: Music2, genres: Tags, folders: Folder }
</script>

<template>
  <div class="flex flex-col gap-3">
    <PageHeader :title="t('nav.libraryMenu')" />
    <nav :aria-label="t('nav.libraryMenu')" class="-mx-5 flex gap-1 overflow-x-auto border-b border-line px-5 [scrollbar-width:none] md:mx-0 md:px-0">
      <RouterLink
        v-for="name in LIBRARY_ROUTES"
        :key="name"
        :to="{ name }"
        class="-mb-px flex h-11 flex-none items-center gap-1 border-b-2 px-2 text-[16px] transition-colors md:gap-1.5 md:px-3"
        :class="route.name === name ? 'border-ink font-semibold' : 'border-transparent font-light text-muted hover:text-ink'"
        :aria-current="route.name === name ? 'page' : undefined"
      >
        <component :is="ICONS[name]" :size="16" :stroke-width="route.name === name ? 2 : 1.6" aria-hidden="true" />{{ t(LABELS[name]) }}
      </RouterLink>
    </nav>
    <SearchField v-if="search !== undefined" v-model="search" :placeholder="searchLabel ?? ''" class="mt-1 w-full sm:max-w-sm" />
    <!-- on a narrow screen the controls go to their own line rather than squeeze the count -->
    <div v-if="sub || $slots.default" class="flex min-h-8 flex-wrap items-center justify-between gap-x-3 gap-y-2">
      <p class="whitespace-nowrap text-[15px] font-light text-muted">{{ sub }}</p>
      <div v-if="$slots.default" class="ml-auto flex-none"><slot /></div>
    </div>
  </div>
</template>
