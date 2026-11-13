<script setup lang="ts">
import { useRoute } from 'vue-router'
import { type Component } from 'vue'
import { useI18n } from 'vue-i18n'
import { AudioLines, Disc3, Folder, MicVocal, Music2, Search, Tags, X } from '@lucide/vue'
import { LIBRARY_ROUTES, type LibraryRoute } from '../router'
import PageHeader from './PageHeader.vue'

// The library's pages (albums, artists, songs, covers, genres, folders) share one header: the title and
// their tabs (the slot sits right of the count line). Each tab is its own route, so lists stay alive
// and back/forward move between them. Searching narrows the tab itself (its kind alone): from the
// top bar on a PC (App.vue). On a phone the 🔍 by the title searches the whole library, kind by kind
// (LibrarySearchView); a tab opened from there stays searched, shown (and cleared) under the tabs.
defineProps<{ sub?: string; searchLabel?: string }>()
const search = defineModel<string>('search')
const { t } = useI18n()
const route = useRoute()


const LABELS: Record<LibraryRoute, string> = {
  albums: 'nav.albums',
  artists: 'nav.artists',
  tracks: 'nav.songs',
  covers: 'nav.covers',
  genres: 'nav.genres',
  folders: 'nav.folders',
}
const ICONS: Record<LibraryRoute, Component> = { albums: Disc3, artists: MicVocal, tracks: Music2, covers: AudioLines, genres: Tags, folders: Folder }
</script>

<template>
  <div class="flex flex-col gap-3">
    <PageHeader :title="t('nav.libraryMenu')">
      <template #actions>
        <RouterLink :to="{ name: 'library-search' }" class="grid size-10 place-items-center rounded-full bg-surface md:hidden" :aria-label="t('libSearch.title')" :title="t('libSearch.title')">
          <Search :size="19" :stroke-width="1.6" />
        </RouterLink>
      </template>
    </PageHeader>
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
    <div v-if="search?.trim()" class="flex md:hidden">
      <span class="flex h-9 min-w-0 items-center gap-1.5 rounded-full bg-surface pl-3 pr-1 text-[14px]">
        <Search :size="15" :stroke-width="1.6" class="flex-none text-muted" /><span class="truncate">{{ t('search.resultsFor', { q: search.trim() }) }}</span>
        <button type="button" class="grid size-7 flex-none place-items-center rounded-full text-muted hover:text-ink" :aria-label="t('libSearch.clear')" @click="search = ''"><X :size="15" /></button>
      </span>
    </div>
    <!-- on a narrow screen the controls go to their own line rather than squeeze the count -->
    <div v-if="sub || $slots.default" class="flex min-h-8 flex-wrap items-center justify-between gap-x-3 gap-y-2">
      <p class="whitespace-nowrap text-[15px] font-light text-muted">{{ sub }}</p>
      <div v-if="$slots.default" class="ml-auto flex-none"><slot /></div>
    </div>
  </div>
</template>
