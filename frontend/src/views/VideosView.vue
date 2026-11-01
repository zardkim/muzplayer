<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Film, FolderPlus, Play } from '@lucide/vue'
import { api, query } from '../api'
import { errorMessage } from '../i18n'
import { useUi } from '../stores/ui'
import { VIDEO_KINDS, type VideoKind, type VideoListItem } from '../types'
import CoverArt from '../components/CoverArt.vue'
import PageHeader from '../components/PageHeader.vue'
import VideoFilesSheet from '../components/VideoFilesSheet.vue'
import YoutubeIcon from '../components/YoutubeIcon.vue'

// Music videos: the YouTube videos added to songs and albums (album page, a song's menu) and the
// video files registered from the NAS (library/video), by kind. A YouTube video plays in the video
// sheet with the other videos of its song or album; a file in its own sheet (App.vue).
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
// the list may have changed in a sheet (a video added, removed or moved to another kind)
watch(() => !!(ui.videoTarget || ui.fileVideo || addingFiles.value), (open, was) => was && !open && load())

function play(v: VideoListItem) {
  if (v.source === 'file') {
    ui.fileVideo = v
    return
  }
  const tg = v.target!
  ui.videoTarget = v.track_id
    ? { trackId: v.track_id, title: tg.title, artist: tg.artist, play: v.id }
    : { albumId: v.album_id!, title: tg.title, artist: tg.artist, play: v.id }
}

const thumb = (id: string) => `https://i.ytimg.com/vi/${id}/mqdefault.jpg`
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

    <p v-if="error" class="font-light text-muted">{{ error }}</p>
    <p v-else-if="!loading && !items.length" class="max-w-xl font-light leading-relaxed text-muted">{{ t('videos.pageEmpty') }}</p>

    <section v-for="s in sections" :key="s.kind" class="flex flex-col gap-3">
      <h2 v-if="!kind" class="text-[19px] font-bold">{{ t(`videos.kinds.${s.kind}`) }} <span class="text-[14px] font-normal text-muted">{{ s.items.length }}</span></h2>
      <ul class="grid grid-cols-1 gap-x-4 gap-y-6 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        <li v-for="v in s.items" :key="v.id" class="flex flex-col gap-2.5">
          <button type="button" class="group relative aspect-video overflow-hidden rounded-xl bg-surface" :aria-label="`${t('videos.play')}: ${v.title}`" @click="play(v)">
            <img v-if="v.youtube_id" :src="thumb(v.youtube_id)" alt="" loading="lazy" class="h-full w-full object-cover transition-transform group-hover:scale-[1.03]" />
            <span v-else class="grid h-full w-full place-items-center bg-ink/90 text-on-ink/70"><Film :size="40" :stroke-width="1.1" /></span>
            <span class="absolute inset-0 m-auto grid size-12 place-items-center rounded-full bg-black/55 text-white"><Play :size="20" fill="currentColor" /></span>
            <span class="absolute left-2 top-2 flex items-center gap-1 rounded-full bg-black/60 px-2 text-[11px] leading-5 text-white">
              <YoutubeIcon v-if="v.youtube_id" :size="13" /><template v-else>{{ t('videos.nas') }}</template>
            </span>
          </button>
          <span class="line-clamp-2 text-[15px] leading-snug">{{ v.title }}</span>
          <!-- the song or album it belongs to -->
          <RouterLink
            v-if="v.target?.album_id"
            :to="{ name: 'album', params: { id: v.target.album_id } }"
            class="flex min-w-0 items-center gap-2.5 text-[13px] text-muted hover:text-ink"
          >
            <CoverArt :album-id="v.target.album_id" :has-cover="v.target.has_cover" :version="v.target.cover_v" rounded="rounded" class="size-8 flex-none" />
            <span class="flex min-w-0 flex-col">
              <span class="truncate text-ink">{{ v.target.title }}</span>
              <span class="truncate">{{ v.target.type === 'track' ? t('videos.forSong') : t('videos.forAlbumShort') }} · {{ v.target.artist || t('common.unknownArtist') }}</span>
            </span>
          </RouterLink>
          <span v-else-if="v.file_path" class="truncate text-[13px] text-muted">{{ v.file_path }}</span>
        </li>
      </ul>
    </section>

    <button v-if="items.length < total" type="button" class="h-11 self-center rounded-full border border-line-strong px-6 text-[15px] disabled:opacity-40" :disabled="loading" @click="load(true)">
      {{ t('videos.more') }}
    </button>

    <VideoFilesSheet v-if="addingFiles" @close="addingFiles = false" />
  </div>
</template>
