<script setup lang="ts">
import { onDeactivated, onMounted, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { ExternalLink, Maximize2, X } from '@lucide/vue'
import { usePlayer } from '../stores/player'
import { useUi } from '../stores/ui'
import type { VideoListItem } from '../types'
import { youtubeApi, type YTPlayer } from '../youtube'

// A video card's own player (ui.inlineVideo): the picture turns into the video where it is, as on
// YouTube's lists; one at a time. YouTube ones with YouTube's player, NAS files with the browser's.
// The music pauses while it plays. ⤢ hands it to the large video player, with the page's others after it.
const props = defineProps<{ video: VideoListItem }>()
const emit = defineEmits<{ expand: [] }>()
const { t } = useI18n()
const ui = useUi()
const player = usePlayer()
const host = ref<HTMLElement | null>(null)
const playError = ref<'embed' | 'gone' | null>(null)
let yt: YTPlayer | null = null

function pauseMusic() {
  if (player.playing) player.toggle()
}
function close() {
  if (ui.inlineVideo === props.video.id) ui.inlineVideo = null
}

onMounted(async () => {
  const id = props.video.youtube_id
  if (!id) return // the <video> element plays it
  const YT = await youtubeApi()
  if (!host.value) return // closed meanwhile
  const el = document.createElement('div') // YouTube replaces it with its iframe: one Vue doesn't track
  host.value.replaceChildren(el)
  yt = new YT.Player(el, {
    host: 'https://www.youtube-nocookie.com',
    videoId: id,
    width: '100%',
    height: '100%',
    playerVars: { autoplay: 1, playsinline: 1, rel: 0 },
    events: {
      onStateChange: (e: { data: number }) => {
        if (e.data === YT.PlayerState.PLAYING) pauseMusic()
        if (e.data === YT.PlayerState.ENDED) close()
      },
      // 101/150: its owner allows YouTube only; 100: removed or private
      onError: (e: { data: number }) => (playError.value = e.data === 100 ? 'gone' : 'embed'),
    },
  })
})
// the large player opened (play all, shuffle) or the page left: this one stops (and doesn't start
// again by itself on coming back)
onUnmounted(() => {
  yt?.destroy()
  close()
})
watch(() => ui.videoQueue, (q) => q && close())
onDeactivated(close)
</script>

<template>
  <div class="relative aspect-video overflow-hidden rounded-xl bg-black">
    <video
      v-if="!video.youtube_id"
      :src="`/api/v1/videos/${video.id}/file`"
      controls
      autoplay
      playsinline
      class="absolute inset-0 h-full w-full"
      @play="pauseMusic"
      @ended="close"
      @error="playError = 'embed'"
    />
    <div v-else ref="host" class="absolute inset-0" />
    <div v-if="playError" class="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-ink p-3 text-center text-[13px] text-on-ink">
      <p>{{ !video.youtube_id ? t('videos.fileCantPlay') : playError === 'gone' ? t('videos.unavailable') : t('videos.notEmbeddable') }}</p>
      <a v-if="video.youtube_id" :href="`https://www.youtube.com/watch?v=${video.youtube_id}`" target="_blank" rel="noopener" class="flex h-9 items-center gap-1.5 rounded-full bg-bg px-3.5 text-ink">
        <ExternalLink :size="15" />{{ t('videos.openYoutube') }}
      </a>
    </div>
    <!-- top right, clear of YouTube's own controls (bottom) and title (top left) -->
    <div class="absolute right-1.5 top-1.5 flex gap-1">
      <button type="button" class="grid size-8 place-items-center rounded-full bg-black/60 text-white" :aria-label="t('videos.openLarge')" :title="t('videos.openLarge')" @click="emit('expand')">
        <Maximize2 :size="15" />
      </button>
      <button type="button" class="grid size-8 place-items-center rounded-full bg-black/60 text-white" :aria-label="t('videos.stopInline')" :title="t('videos.stopInline')" @click="close">
        <X :size="16" />
      </button>
    </div>
  </div>
</template>
