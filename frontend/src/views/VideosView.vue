<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { ArrowDownUp, AudioLines, FolderPlus, Heart, LayoutGrid, Play, Shuffle } from '@lucide/vue'
import { api, query } from '../api'
import { errorMessage } from '../i18n'
import { useAuth } from '../stores/auth'
import { useUi } from '../stores/ui'
import { VIDEO_KINDS, type VideoKind, type VideoListItem } from '../types'
import PageHeader from '../components/PageHeader.vue'
import SearchField from '../components/SearchField.vue'
import SelectPill from '../components/SelectPill.vue'
import { useListSearch } from '../listSearch'
import VideoFilesSheet from '../components/VideoFilesSheet.vue'
import ExtractJobsSheet from '../components/ExtractJobsSheet.vue'
import ExtractStartSheet from '../components/ExtractStartSheet.vue'
import YoutubeAddSheet from '../components/YoutubeAddSheet.vue'
import YoutubeIcon from '../components/YoutubeIcon.vue'
import VideoCard from '../components/VideoCard.vue'
import LoadMore from '../components/LoadMore.vue'

// Music videos: the YouTube videos added to songs and albums (album page, a song's menu) and the
// video files an admin registered from the NAS (library/video), by kind. A video plays large in the video
// player (App.vue), the others of the page after it; or all of them, shuffled.
const { t } = useI18n()
const ui = useUi()
const auth = useAuth()
const PAGE = 200

const items = ref<VideoListItem[]>([])
const total = ref(0)
const loading = ref(false)
const error = ref('')
const addingFiles = ref(false)
const extracting = ref<VideoListItem | null>(null) // admin: a video's sound as a song (ExtractStartSheet)
const extractJobs = ref(false)
const addingYoutube = ref(false)
const kind = computed({
  get: () => (ui.views.videoKind as VideoKind | undefined) || null,
  set: (v: VideoKind | null) => (ui.views = { ...ui.views, videoKind: v ?? '' }),
})
// only the videos this person liked (with a kind, or all of them)
const likedOnly = computed({
  get: () => ui.views.videoLiked === '1',
  set: (v: boolean) => (ui.views = { ...ui.views, videoLiked: v ? '1' : '' }),
})
// the order within each kind, remembered like the filters
const SORTS = ['recent', 'oldest', 'title', 'artist'] as const
const sort = computed({
  get: () => ((SORTS as readonly string[]).includes(ui.views.videoSort ?? '') ? ui.views.videoSort : 'recent'),
  set: (v: string) => (ui.views = { ...ui.views, videoSort: v }),
})
// all kinds: a section per kind; one kind: just its videos
const sections = computed(() =>
  (kind.value ? [kind.value] : VIDEO_KINDS)
    .map((k) => ({ kind: k, items: items.value.filter((v) => v.kind === k) }))
    .filter((s) => s.items.length),
)

const q = useListSearch(() => load())
let asked = 0

async function load(more = false) {
  const mine = ++asked
  loading.value = true
  error.value = ''
  try {
    const r = await api<{ items: VideoListItem[]; total: number }>(
      `/videos${query({ q: q.value.trim() || undefined, kind: kind.value ?? undefined, liked: likedOnly.value ? 'true' : undefined, sort: sort.value, offset: more ? items.value.length : 0, limit: PAGE })}`,
    )
    if (mine !== asked) return
    items.value = more ? [...items.value, ...r.items] : r.items
    total.value = r.total
  } catch (e) {
    error.value = errorMessage(e)
  } finally {
    if (mine === asked) loading.value = false
  }
}
onMounted(() => load())
watch([kind, likedOnly, sort], () => load())
// a video's song picked (the link sheet): its card shows it
watch(() => ui.videoLinked, () => load())
// unliked while only liked ones show: it goes
function liked(v: VideoListItem, on: boolean) {
  v.is_favorite = on
  if (likedOnly.value && !on) load()
}
// NAS files were added: the list follows
watch(addingFiles, (open) => !open && load())

// the page's videos in the order shown (by kind), from the one picked
const shown = computed(() => sections.value.flatMap((s) => s.items))
function play(v: VideoListItem) {
  ui.videoQueue = { items: shown.value, start: shown.value.indexOf(v) }
}
function playAll(shuffle: boolean) {
  const items = shown.value
  if (items.length) ui.videoQueue = { items, start: shuffle ? Math.floor(Math.random() * items.length) : 0, shuffle }
}
</script>

<template>
  <div class="flex flex-col gap-6">
    <PageHeader :title="t('videos.pageTitle')" :sub="total ? t('videos.pageSub', { n: total }) : ''">
      <template #actions>
        <!-- songs taken out of videos (extract.py) -->
        <button v-if="auth.user?.is_admin" type="button" class="grid size-10 place-items-center rounded-full bg-surface hover:bg-surface-2" :aria-label="t('extract.jobsTitle')" :title="t('extract.jobsTitle')" @click="extractJobs = true">
          <AudioLines :size="18" :stroke-width="1.6" />
        </button>
        <button v-if="auth.user?.is_admin" type="button" class="flex h-10 items-center gap-1.5 rounded-full bg-surface px-3 text-[14px] hover:bg-surface-2 sm:px-4" :aria-label="t('videos.addYoutube')" :title="t('videos.addYoutube')" @click="addingYoutube = true">
          <YoutubeIcon :size="18" /><span class="max-sm:hidden">{{ t('videos.addYoutube') }}</span>
        </button>
        <button v-if="auth.user?.is_admin" type="button" class="flex h-10 items-center gap-1.5 rounded-full bg-ink px-3 text-[14px] text-on-ink sm:px-4" :aria-label="t('videos.addFile')" :title="t('videos.addFile')" @click="addingFiles = true">
          <FolderPlus :size="17" :stroke-width="1.6" /><span class="max-sm:hidden">{{ t('videos.addFile') }}</span>
        </button>
      </template>
    </PageHeader>

    <!-- a search, liked only, the kind and the order -->
    <div class="flex flex-wrap items-center gap-2">
      <SearchField v-model="q" :placeholder="t('videos.searchVideos')" class="w-full sm:w-72" />
      <!-- liked, kind, order: one line on a phone too (liked shows just its heart there) -->
      <div class="flex w-full min-w-0 items-center gap-2 sm:w-auto">
        <button
          type="button"
          class="flex h-[38px] flex-none items-center gap-1.5 rounded-full border px-3 text-[15px] sm:px-4"
          :class="likedOnly ? 'border-like bg-like text-white' : 'border-line-strong bg-bg'"
          :aria-pressed="likedOnly"
          :aria-label="t('videos.liked')"
          :title="t('videos.liked')"
          @click="likedOnly = !likedOnly"
        >
          <Heart :size="15" :stroke-width="1.8" :fill="likedOnly ? 'currentColor' : 'none'" /><span class="max-sm:hidden">{{ t('videos.liked') }}</span>
        </button>
        <SelectPill v-model="kind" fill :label="t('videos.kind')" :icon="LayoutGrid" :options="[{ value: null, label: t('videos.all') }, ...VIDEO_KINDS.map((k) => ({ value: k, label: t(`videos.kinds.${k}`) }))]" />
        <SelectPill v-model="sort" fill :label="t('videos.sort')" :icon="ArrowDownUp" :options="SORTS.map((s) => ({ value: s, label: t(`videos.sorts.${s}`) }))" />
      </div>
    </div>

    <div v-if="items.length" class="-mt-2 flex gap-2">
      <button type="button" class="flex h-10 items-center gap-1.5 rounded-full bg-ink px-4 text-[14px] text-on-ink" @click="playAll(false)">
        <Play :size="15" fill="currentColor" />{{ t('videos.playAll') }}
      </button>
      <button type="button" class="flex h-10 items-center gap-1.5 rounded-full border border-line-strong px-4 text-[14px]" @click="playAll(true)">
        <Shuffle :size="16" :stroke-width="1.6" />{{ t('videos.shufflePlay') }}
      </button>
    </div>

    <p v-if="error" class="font-light text-muted">{{ error }}</p>
    <p v-else-if="!loading && !items.length" class="max-w-xl font-light leading-relaxed text-muted">{{ q.trim() ? t('search.noResults') : t('videos.pageEmpty') }}</p>

    <section v-for="s in sections" :key="s.kind" class="flex flex-col gap-3">
      <h2 v-if="!kind" class="text-[19px] font-bold">{{ t(`videos.kinds.${s.kind}`) }} <span class="text-[14px] font-normal text-muted">{{ s.items.length }}</span></h2>
      <ul class="grid grid-cols-1 gap-x-4 gap-y-6 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        <li v-for="v in s.items" :key="v.id">
          <VideoCard :video="v" @play="play(v)" @changed="load()" @liked="(on) => liked(v, on)" @extract="extracting = v" />
        </li>
      </ul>
    </section>

    <LoadMore v-if="items.length < total" :loading="loading" @click="load(true)" />

    <VideoFilesSheet v-if="addingFiles" @close="addingFiles = false" />
    <ExtractStartSheet v-if="extracting" :video="extracting" @close="extracting = null" @queued="(extracting = null), (extractJobs = true)" />
    <ExtractJobsSheet v-if="extractJobs" @close="extractJobs = false" />
    <YoutubeAddSheet v-if="addingYoutube" @close="addingYoutube = false" @added="load()" />
  </div>
</template>
