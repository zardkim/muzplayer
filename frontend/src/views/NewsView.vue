<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { Bell } from '@lucide/vue'
import { ago } from '../format'
import { loadNews, markNewsSeen, type News } from '../news'
import { useUi } from '../stores/ui'
import type { VideoListItem } from '../types'
import AlbumGrid from '../components/AlbumGrid.vue'
import BookGrid from '../components/BookGrid.vue'
import ChartGrid from '../components/ChartGrid.vue'
import PageHeader from '../components/PageHeader.vue'
import VideoCard from '../components/VideoCard.vue'

// What was added since this person last looked (the bell): albums, audiobooks, music videos, charts
// and themes. Opening it counts as seeing them; they stay on the page until it is left.
const { t } = useI18n()
const ui = useUi()
const shown = ref<News | null>(null)
const loaded = ref(false)

onMounted(async () => {
  const n = await loadNews(true)
  shown.value = n && { ...n, counts: { ...n.counts } }
  loaded.value = true
  markNewsSeen()
})

const c = computed(() => shown.value?.counts ?? {})
const charts = computed(() => shown.value?.charts.filter((x) => x.kind === 'chart') ?? [])
const themes = computed(() => shown.value?.charts.filter((x) => x.kind === 'theme') ?? [])
function play(v: VideoListItem) {
  const items = shown.value!.videos
  ui.videoQueue = { items, start: items.indexOf(v) }
}
// a section's heading: its count of all, and how many of them are below when not all are
const more = (all: number | undefined, here: number) => (all && all > here ? t('news.showing', { n: here }) : '')
</script>

<template>
  <div class="flex flex-col gap-8">
    <PageHeader :title="t('news.title')" :icon="Bell" :sub="shown?.total ? t('news.since', { when: ago(shown.since) }) : undefined" />
    <p v-if="loaded && !shown?.total" class="font-light text-muted">{{ t('news.empty') }}</p>

    <section v-if="shown?.albums.length" class="flex flex-col gap-3">
      <h2 class="text-[19px] font-bold">{{ t('news.albums') }} <span class="text-[14px] font-normal text-muted">{{ c.albums }} {{ more(c.albums, shown.albums.length) }}</span></h2>
      <AlbumGrid :albums="shown.albums" />
    </section>
    <section v-if="shown?.books.length" class="flex flex-col gap-3">
      <h2 class="text-[19px] font-bold">{{ t('news.books') }} <span class="text-[14px] font-normal text-muted">{{ c.books }} {{ more(c.books, shown.books.length) }}</span></h2>
      <BookGrid :books="shown.books" />
    </section>
    <section v-if="shown?.videos.length" class="flex flex-col gap-3">
      <h2 class="text-[19px] font-bold">{{ t('news.videos') }} <span class="text-[14px] font-normal text-muted">{{ c.videos }} {{ more(c.videos, shown.videos.length) }}</span></h2>
      <ul class="grid grid-cols-1 gap-x-4 gap-y-6 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        <li v-for="v in shown.videos" :key="v.id"><VideoCard :video="v" @play="play(v)" /></li>
      </ul>
    </section>
    <section v-if="charts.length" class="flex flex-col gap-3">
      <h2 class="text-[19px] font-bold">{{ t('news.charts') }} <span class="text-[14px] font-normal text-muted">{{ c.charts }} {{ more(c.charts, charts.length) }}</span></h2>
      <ChartGrid :charts="charts" />
    </section>
    <section v-if="themes.length" class="flex flex-col gap-3">
      <h2 class="text-[19px] font-bold">{{ t('news.themes') }} <span class="text-[14px] font-normal text-muted">{{ c.themes }} {{ more(c.themes, themes.length) }}</span></h2>
      <ChartGrid :charts="themes" />
    </section>
  </div>
</template>
