<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Film } from '@lucide/vue'
import { useUi } from '../stores/ui'
import type { Video } from '../types'
import { youtubeThumb } from '../youtube'

// A video's picture, filling its (positioned) box: YouTube's own, or the thumbnail the server made
// of a NAS file (video_thumbs.py; the film icon while there is none). NAS files show their length.
const props = withDefaults(defineProps<{ video: Pick<Video, 'id' | 'youtube_id'> & { duration?: number | null; thumb_v?: number | null }; icon?: number; length?: boolean }>(), {
  icon: 22,
  length: true,
})
const ui = useUi()
const failed = ref(false)
watch(() => props.video.id, () => (failed.value = false))
// ?v: the way thumbnails are made (video_thumbs.VERSION) and when this one was: a new one is a new
// address, so one seen is kept on the device (sw.js) and not fetched again while scrolling
const src = computed(() => {
  if (props.video.youtube_id) return youtubeThumb(props.video.youtube_id)
  const bust = ui.thumbBust[props.video.id]
  return `/api/v1/videos/${props.video.id}/thumb?v=2-${props.video.thumb_v ?? 0}${bust ? `&t=${bust}` : ''}`
})
watch(src, () => (failed.value = false))
const time = computed(() => {
  const s = props.video.duration
  if (!s) return ''
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const ss = String(s % 60).padStart(2, '0')
  return h ? `${h}:${String(m).padStart(2, '0')}:${ss}` : `${m}:${ss}`
})
</script>

<template>
  <span class="absolute inset-0 block">
    <img v-if="!failed" :src="src" alt="" loading="lazy" decoding="async" class="h-full w-full object-cover transition-transform group-hover:scale-[1.03]" @error="failed = true" />
    <span v-else class="grid h-full w-full place-items-center bg-ink/90 text-on-ink/70"><Film :size="icon" :stroke-width="1.2" /></span>
    <span v-if="length && time" class="absolute bottom-1.5 right-1.5 rounded bg-black/75 px-1 text-[11px] leading-4 text-white">{{ time }}</span>
  </span>
</template>
