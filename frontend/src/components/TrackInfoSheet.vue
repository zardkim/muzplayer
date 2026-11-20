<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api'
import { errorMessage } from '../i18n'
import { dateTime, duration } from '../format'
import type { Track } from '../types'
import InfoSheet, { type InfoRow, type InfoTab } from './InfoSheet.vue'

// A song's file (the song menu's "info"): where it is in the library, its size and dates, how it is
// encoded (read from the file as it is now) and every tag the scan read.
const props = defineProps<{ track: Track }>()
const emit = defineEmits<{ close: [] }>()
const { t } = useI18n()

interface Info {
  path: string
  folder: string
  file: string
  size: number
  modified: string
  added: string
  missing: boolean
  scan_error: string | null
  format: string
  duration: number | null
  sample_rate: number | null
  bit_depth: number | null
  bitrate: number | null
  lossless: boolean
  replaygain: Record<string, number>
  lyrics: { tags: boolean; file: boolean }
  stream: Record<string, string | number>
  tags: Record<string, string[]>
}
const info = ref<Info | null>(null)
const error = ref('')
onMounted(async () => {
  try {
    info.value = await api<Info>(`/tracks/${props.track.id}/info`)
  } catch (e) {
    error.value = errorMessage(e)
  }
})

// paths as on disk may be spelled apart (NFD, from a Mac): shown composed
const nfc = (s: string) => s.normalize('NFC')
const size = (b: number) => (b >= 1024 * 1024 ? `${(b / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(b / 1024))} KB`)
const kbps = (bps: number) => `${Math.round(bps / 1000)} kbps`

// a tab per part: the file, how it is encoded, its tags (only what is known)
const row = (label: string, value: string): InfoRow => ({ label, value })
const tabs = computed<InfoTab[]>(() => {
  const x = info.value
  if (!x) return []
  const file = [
    row(t('trackInfo.folder'), nfc(x.folder)),
    row(t('trackInfo.file'), nfc(x.file)),
    row(t('trackInfo.size'), size(x.size)),
    row(t('trackInfo.modified'), dateTime(x.modified)),
    row(t('trackInfo.added'), dateTime(x.added)),
    ...(x.missing ? [row(t('trackInfo.state'), t('common.missingFile'))] : []),
    ...(x.scan_error ? [row(t('common.scanError'), x.scan_error)] : []),
  ]
  const s = x.stream
  const encoding = [row(t('trackInfo.format'), `${x.format.toUpperCase()}${x.lossless ? ` · ${t('albums.quality_lossless')}` : ''}`)]
  if (s.codec_description || s.codec) encoding.push(row(t('trackInfo.codec'), String(s.codec_description ? `${s.codec_description} (${s.codec ?? ''})`.replace(' ()', '') : s.codec)))
  if (x.duration) encoding.push(row(t('trackInfo.length'), duration(x.duration)))
  const rate = Number(s.sample_rate || x.sample_rate || 0)
  if (rate) encoding.push(row(t('trackInfo.sampleRate'), `${(rate / 1000).toLocaleString()} kHz`))
  const bits = Number(s.bits_per_sample || x.bit_depth || 0)
  if (bits && x.lossless) encoding.push(row(t('trackInfo.bitDepth'), `${bits} bit`))
  const rateBps = Number(s.bitrate || (x.bitrate ? x.bitrate * 1000 : 0))
  if (rateBps) encoding.push(row(t('trackInfo.bitrate'), `${kbps(rateBps)}${s.bitrate_mode && s.bitrate_mode !== 'UNKNOWN' ? ` (${s.bitrate_mode})` : ''}`))
  if (s.channels) encoding.push(row(t('trackInfo.channels'), `${s.channels}${s.mode ? ` (${s.mode})` : ''}`))
  if (s.encoder_info) encoding.push(row(t('trackInfo.encoder'), String(s.encoder_info)))
  if (s.encoder_settings) encoding.push(row(t('trackInfo.encoderSettings'), String(s.encoder_settings)))
  const rg = x.replaygain
  if (rg.rg_track_gain != null) encoding.push(row(t('trackInfo.rgTrack'), `${rg.rg_track_gain.toFixed(2)} dB`))
  if (rg.rg_album_gain != null) encoding.push(row(t('trackInfo.rgAlbum'), `${rg.rg_album_gain.toFixed(2)} dB`))
  encoding.push(row(t('trackInfo.lyrics'), [x.lyrics.tags ? t('trackInfo.lyricsTags') : '', x.lyrics.file ? t('trackInfo.lyricsFile') : ''].filter(Boolean).join(', ') || t('trackInfo.none')))
  return [
    { key: 'file', label: t('trackInfo.fileTitle'), rows: file },
    { key: 'encoding', label: t('trackInfo.encodingTitle'), rows: encoding },
    { key: 'tags', label: t('trackInfo.tagsTitle'), rows: Object.entries(x.tags).map(([k, v]) => row(k, v.join(' / '))) },
  ]
})
</script>

<template>
  <InfoSheet :title="t('trackInfo.title')" :subtitle="`${track.title}${track.artist ? ` · ${track.artist}` : ''}`" :tabs="tabs" :error="error" @close="emit('close')" />
</template>
