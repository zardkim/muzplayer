<script setup lang="ts">
import { getCurrentInstance, inject, onActivated, onDeactivated, onMounted, onUnmounted, type Component } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import {
  Bell, BookHeadphones, ChartColumn, ChartNoAxesColumn, ChevronLeft, Clapperboard, Disc3, Download, Heart, History, House, LibraryBig,
  ListMusic, ListVideo, Radio, ScrollText, Search, Settings, Sparkles, Tags, User, Users,
} from '@lucide/vue'
import { PAGE_BACK, type PageBack } from '../pageBack'
import Marquee from './Marquee.vue'

// Large page title (mobile style), with the page's icon in front; on a phone, back (‹) sits on the
// same line (App.vue then leaves out its own back line). The account menu is in the sidebar (PC)
// and the tab bar (phone). `icon`: one of its own (a settings part, a smart playlist); otherwise
// the page's, by route.
const props = defineProps<{ title: string; sub?: string; icon?: Component }>()
const { t } = useI18n()
const route = useRoute()

const ICONS: Record<string, Component> = {
  home: House, search: Search, albums: LibraryBig, artists: LibraryBig, tracks: LibraryBig, genres: LibraryBig, folders: LibraryBig,
  charts: ChartNoAxesColumn, 'chart-list': ChartNoAxesColumn, radio: Radio, videos: Clapperboard, 'video-playlist': ListVideo,
  books: BookHeadphones, library: User, playlists: ListMusic, playlist: ListMusic, mix: Sparkles, favorites: Heart, history: History,
  news: Bell, downloads: Download, playing: Disc3, settings: Settings, admin: Users, logs: ScrollText, stats: ChartColumn,
}
const icon = () => props.icon ?? (route.name === 'tracks' && route.query.genre ? Tags : ICONS[String(route.name)])

// this header carries back: App's own back line steps aside while one is on the page
const back = inject<PageBack | null>(PAGE_BACK, null)
const uid = getCurrentInstance()!.uid
const claim = () => back?.owners.add(uid)
const release = () => back?.owners.delete(uid)
onMounted(claim)
onActivated(claim)
onDeactivated(release)
onUnmounted(release)
</script>

<template>
  <div class="flex flex-col gap-1">
    <div class="flex items-center justify-between gap-3">
      <div class="flex min-w-0 items-center gap-2 md:gap-2.5">
        <button v-if="back?.show.value" type="button" class="-ml-2.5 -mr-1 grid size-10 flex-none place-items-center rounded-full md:hidden" :aria-label="t('nav.back')" @click="back.go()">
          <ChevronLeft :size="28" :stroke-width="1.5" />
        </button>
        <component :is="icon()" v-if="icon()" :size="28" :stroke-width="2" class="flex-none md:size-9" aria-hidden="true" />
        <Marquee as="h1" :text="title" class="text-[34px] font-extrabold leading-tight tracking-tight md:text-[40px]" />
      </div>
      <div class="flex items-center gap-1">
        <slot name="actions" />
      </div>
    </div>
    <p v-if="sub" class="text-[15px] font-light text-muted">{{ sub }}</p>
  </div>
</template>
