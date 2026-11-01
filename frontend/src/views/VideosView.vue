<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { FolderPlus, Play, Shuffle } from '@lucide/vue'
import { api, query } from '../api'
import { errorMessage } from '../i18n'
import { useUi } from '../stores/ui'
import { VIDEO_KINDS, type VideoKind, type VideoListItem } from '../types'
import PageHeader from '../components/PageHeader.vue'
import VideoFilesSheet from '../components/VideoFilesSheet.vue'
import VideoCard from '../components/VideoCard.vue'

// Music videos: the YouTube videos added to songs and albums (album page, a song's menu) and the
// video files registered from the NAS (library/video), by kind. A video plays large in the video
// player (App.vue), the others of the page after it; or all of them, shuffled.
const { t } = useI18n()
const ui = useUi()
const PAGE = 200

const items = ref<VideoListItem[]>([])
const total = ref(0)
const loading = ref(false)
const error = ref('')
const addingFiles = ref(false)
const kind = computed({
  get: () => (ui.views.videoKind as VideoKind | undefined) || null,
  set: (v: VideoKind | null) => (ui.views = { ...ui.views, videoKind: v ?? '' }),
})
// all kinds: a section per kind; one kind: just its videos
const sections = computed(() =>
  (kind.value ? [kind.value] : VIDEO_KINDS)
    .map((k) => ({ kind: k, items: items.value.filter((v) => v.kind === k) }))
    .filter((s) => s.items.length),
)

async function load(more = false) {
  loading.value = true
  error.value = ''
  try {
    const r = await api<{ items: VideoListItem[]; total: number }>(
      `/videos${query({ kind: kind.value ?? undefined, offset: more ? items.value.length : 0, limit: PAGE })}`,
    )
    items.value = more ? [...items.value, ...r.items] : r.items
    total.value = r.total
  } catch (e) {
    error.value = errorMessage(e)
  } finally {
    loading.value = false
  }
}
onMounted(() => load())
watch(kind, () => load())
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
    <PageHeader :title="t('videos.pageTitle')" :sub="total ? t('videos.pageSub', { n: total }) : ''" />

    <div class="flex items-start gap-3">
      <div class="-mr-5 flex min-w-0 flex-1 gap-2 overflow-x-auto pr-5 [scrollbar-width:none] md:mr-0 md:flex-wrap md:pr-0">
        <button
          v-for="k in [null, ...VIDEO_KINDS]"
          :key="k ?? 'all'"
          type="button"
          class="h-[38px] flex-none rounded-full border px-4 text-[15px]"
          :class="kind === k ? 'border-ink bg-ink text-on-ink' : 'border-line-strong bg-bg'"
          :aria-pressed="kind === k"
          @click="kind = k"
        >
          {{ k ? t(`videos.kinds.${k}`) : t('videos.all') }}
        </button>
      </div>
      <button type="button" class="hidden h-[38px] flex-none items-center gap-1.5 rounded-full bg-ink px-4 text-[15px] text-on-ink md:flex" @click="addingFiles = true">
        <FolderPlus :size="17" :stroke-width="1.6" />{{ t('videos.addFile') }}
      </button>
    </div>
    <button type="button" class="-mt-2 flex h-10 items-center gap-1.5 self-start rounded-full bg-ink px-4 text-[14px] text-on-ink md:hidden" @click="addingFiles = true">
      <FolderPlus :size="16" :stroke-width="1.6" />{{ t('videos.addFile') }}
    </button>

    <div v-if="items.length" class="-mt-2 flex gap-2">
      <button type="button" class="flex h-10 items-center gap-1.5 rounded-full bg-ink px-4 text-[14px] text-on-ink" @click="playAll(false)">
        <Play :size="15" fill="currentColor" />{{ t('videos.playAll') }}
      </button>
      <button type="button" class="flex h-10 items-center gap-1.5 rounded-full border border-line-strong px-4 text-[14px]" @click="playAll(true)">
        <Shuffle :size="16" :stroke-width="1.6" />{{ t('videos.shufflePlay') }}
      </button>
    </div>

    <p v-if="error" class="font-light text-muted">{{ error }}</p>
    <p v-else-if="!loading && !items.length" class="max-w-xl font-light leading-relaxed text-muted">{{ t('videos.pageEmpty') }}</p>

    <section v-for="s in sections" :key="s.kind" class="flex flex-col gap-3">
      <h2 v-if="!kind" class="text-[19px] font-bold">{{ t(`videos.kinds.${s.kind}`) }} <span class="text-[14px] font-normal text-muted">{{ s.items.length }}</span></h2>
      <ul class="grid grid-cols-1 gap-x-4 gap-y-6 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        <li v-for="v in s.items" :key="v.id">
          <VideoCard :video="v" @play="play(v)" @changed="load()" />
        </li>
      </ul>
    </section>

    <button v-if="items.length < total" type="button" class="h-11 self-center rounded-full border border-line-strong px-6 text-[15px] disabled:opacity-40" :disabled="loading" @click="load(true)">
      {{ t('videos.more') }}
    </button>

    <VideoFilesSheet v-if="addingFiles" @close="addingFiles = false" />
  </div>
</template>
