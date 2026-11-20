<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api'
import { errorMessage } from '../i18n'
import { dateTime, duration } from '../format'
import type { VideoListItem } from '../types'
import { kindName } from '../videoKinds'
import InfoSheet, { type InfoRow, type InfoTab } from './InfoSheet.vue'

// A music video's details (its ⋮ menu's "info"): what it is, where it is (the NAS file or its YouTube
// link, its song or album) and, a file, how it is encoded (ffmpeg, read when asked).
const props = defineProps<{ video: VideoListItem }>()
const emit = defineEmits<{ close: [] }>()
const { t } = useI18n()

interface Stream {
  type: string
  codec: string
  profile: string | null
  language: string | null
  resolution: string | null
  fps: number | null
  sample_rate: number | null
  channels: string | null
  bitrate: number | null
  details: string
}
interface Info {
  source: 'file' | 'youtube'
  title: string
  kind: string
  channel: string
  duration: number | null
  created_at: string
  added_by: string | null
  likes: number
  youtube_id: string | null
  url?: string
  file_path: string | null
  folder?: string
  file?: string
  exists?: boolean
  size?: number
  modified?: string
  probe?: { container: string | null; bitrate: number | null; streams: Stream[] }
  track: { id: number; title: string; artist: string | null } | null
  album: { id: number; title: string } | null
}
const info = ref<Info | null>(null)
const error = ref('')
onMounted(async () => {
  try {
    info.value = await api<Info>(`/videos/${props.video.id}/info`)
  } catch (e) {
    error.value = errorMessage(e)
  }
})

const nfc = (s: string) => s.normalize('NFC')
const size = (b: number) => (b >= 1024 ** 3 ? `${(b / 1024 ** 3).toFixed(2)} GB` : `${(b / 1024 / 1024).toFixed(1)} MB`)
const row = (label: string, value: string, more: Partial<InfoRow> = {}): InfoRow => ({ label, value, ...more })

const tabs = computed<InfoTab[]>(() => {
  const x = info.value
  if (!x) return []
  const about = [
    row(t('videoInfo.title'), x.title),
    row(t('videos.kind'), kindName(x.kind)),
    row(t('videoInfo.source'), x.source === 'youtube' ? 'YouTube' : t('videoInfo.nas')),
    ...(x.channel ? [row(t('videoInfo.channel'), x.channel)] : []),
    ...(x.duration ? [row(t('trackInfo.length'), duration(x.duration))] : []),
    row(t('videoInfo.added'), [dateTime(x.created_at), x.added_by].filter(Boolean).join(' · ')),
    row(t('videoInfo.likes'), String(x.likes)),
  ]
  // where it is, and what it belongs to
  const where: InfoRow[] = []
  if (x.url) {
    where.push(row(t('videoInfo.link'), x.url, { href: x.url }))
    where.push(row(t('videoInfo.youtubeId'), x.youtube_id ?? ''))
  } else {
    where.push(row(t('trackInfo.folder'), x.folder ? `video/${nfc(x.folder)}` : 'video'))
    where.push(row(t('trackInfo.file'), nfc(x.file ?? '')))
    if (x.size != null) where.push(row(t('trackInfo.size'), size(x.size)))
    if (x.modified) where.push(row(t('trackInfo.modified'), dateTime(x.modified)))
    if (x.exists === false) where.push(row(t('trackInfo.state'), t('common.missingFile')))
  }
  if (x.track) where.push(row(t('videoInfo.song'), `${x.track.title}${x.track.artist ? ` · ${x.track.artist}` : ''}`, x.album ? { to: `/albums/${x.album.id}` } : {}))
  else if (x.album) where.push(row(t('videoInfo.album'), x.album.title, { to: `/albums/${x.album.id}` }))
  else where.push(row(t('videoInfo.linkedTo'), t('videoInfo.notLinked')))
  const out: InfoTab[] = [
    { key: 'about', label: t('videoInfo.aboutTab'), rows: about },
    { key: 'where', label: x.url ? t('videoInfo.linkTab') : t('videoInfo.pathTab'), rows: where },
  ]
  // a file: its container and each stream
  if (x.probe) {
    const codec: InfoRow[] = []
    if (x.probe.container) codec.push(row(t('videoInfo.container'), x.probe.container))
    if (x.probe.bitrate) codec.push(row(t('trackInfo.bitrate'), `${x.probe.bitrate.toLocaleString()} kbps`))
    for (const s of x.probe.streams) {
      const parts = [
        `${s.codec.toUpperCase()}${s.profile ? ` (${s.profile})` : ''}`,
        s.resolution,
        s.fps ? `${s.fps} fps` : null,
        s.sample_rate ? `${(s.sample_rate / 1000).toLocaleString()} kHz` : null,
        s.channels,
        s.bitrate ? `${s.bitrate.toLocaleString()} kbps` : null,
        s.language,
      ].filter(Boolean)
      const label = s.type === 'video' ? t('videoInfo.videoStream') : s.type === 'audio' ? t('videoInfo.audioStream') : s.type === 'subtitle' ? t('videoInfo.subtitleStream') : s.type
      codec.push(row(label, parts.join(' · ')))
    }
    out.push({ key: 'codec', label: t('videoInfo.codecTab'), rows: codec })
  }
  return out
})
</script>

<template>
  <InfoSheet :title="t('videoInfo.heading')" :subtitle="video.title" :tabs="tabs" :error="error" @close="emit('close')" />
</template>
