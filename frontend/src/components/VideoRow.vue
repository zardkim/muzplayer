<script setup lang="ts">
import { onMounted, ref } from 'vue'
import type { RouteLocationRaw } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { api, query } from '../api'
import { useUi } from '../stores/ui'
import type { Page, VideoListItem } from '../types'
import SectionTitle from './SectionTitle.vue'
import VideoThumb from './VideoThumb.vue'

// A row of music videos (home, my music): the newest ones, or this person's liked ones. A tap plays
// the row from that one; the heading opens the whole list. Nothing is shown while there are none.
const props = defineProps<{ title: string; to: RouteLocationRaw; liked?: boolean }>()
const { t } = useI18n()
const ui = useUi()
const items = ref<VideoListItem[]>([])
const total = ref(0)

onMounted(async () => {
  const r = await api<Page<VideoListItem>>(`/videos${query({ liked: props.liked ? 'true' : undefined, sort: 'recent', limit: 12 })}`).catch(() => null)
  if (r) {
    items.value = r.items
    total.value = r.total
  }
})
</script>

<template>
  <section v-if="items.length" class="flex flex-col gap-3">
    <SectionTitle :title="title" :to="to" :count="total" />
    <ul class="-mx-5 flex gap-3 overflow-x-auto px-5 pb-1 [scrollbar-width:none] md:mx-0 md:px-0">
      <li v-for="(v, i) in items" :key="v.id" class="w-[200px] flex-none md:w-[240px]">
        <button type="button" class="group flex w-full flex-col gap-1.5 text-left" :aria-label="`${t('videos.play')}: ${v.title}`" @click="ui.videoQueue = { items, start: i, title }">
          <span class="relative block aspect-video w-full overflow-hidden rounded-xl bg-surface"><VideoThumb :video="v" /></span>
          <span class="line-clamp-2 text-[14px] leading-snug">{{ v.title }}</span>
          <span v-if="v.target" class="-mt-1 truncate text-[12px] text-muted">{{ v.target.artist || v.target.title }}</span>
        </button>
      </li>
    </ul>
  </section>
</template>
