<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api'
import { errorMessage } from '../i18n'
import { dateTime, duration } from '../format'
import type { Track } from '../types'
import BaseModal from './BaseModal.vue'

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

// label, value rows of each part (only what is known)
const file = computed(() => {
  const x = info.value
  if (!x) return []
  return [
    [t('trackInfo.folder'), nfc(x.folder)],
    [t('trackInfo.file'), nfc(x.file)],
    [t('trackInfo.size'), size(x.size)],
    [t('trackInfo.modified'), dateTime(x.modified)],
    [t('trackInfo.added'), dateTime(x.added)],
    ...(x.missing ? [[t('trackInfo.state'), t('common.missingFile')]] : []),
    ...(x.scan_error ? [[t('common.scanError'), x.scan_error]] : []),
  ]
})
const encoding = computed(() => {
  const x = info.value
  if (!x) return []
  const s = x.stream
  const rows: [string, string][] = [
    [t('trackInfo.format'), `${x.format.toUpperCase()}${x.lossless ? ` · ${t('albums.quality_lossless')}` : ''}`],
  ]
  if (s.codec_description || s.codec) rows.push([t('trackInfo.codec'), String(s.codec_description ? `${s.codec_description} (${s.codec ?? ''})`.replace(' ()', '') : s.codec)])
  if (x.duration) rows.push([t('trackInfo.length'), duration(x.duration)])
  const rate = Number(s.sample_rate || x.sample_rate || 0)
  if (rate) rows.push([t('trackInfo.sampleRate'), `${(rate / 1000).toLocaleString()} kHz`])
  const bits = Number(s.bits_per_sample || x.bit_depth || 0)
  if (bits && x.lossless) rows.push([t('trackInfo.bitDepth'), `${bits} bit`])
  const rateBps = Number(s.bitrate || (x.bitrate ? x.bitrate * 1000 : 0))
  if (rateBps) rows.push([t('trackInfo.bitrate'), `${kbps(rateBps)}${s.bitrate_mode && s.bitrate_mode !== 'UNKNOWN' ? ` (${s.bitrate_mode})` : ''}`])
  if (s.channels) rows.push([t('trackInfo.channels'), `${s.channels}${s.mode ? ` (${s.mode})` : ''}`])
  if (s.encoder_info) rows.push([t('trackInfo.encoder'), String(s.encoder_info)])
  if (s.encoder_settings) rows.push([t('trackInfo.encoderSettings'), String(s.encoder_settings)])
  const rg = x.replaygain
  if (rg.rg_track_gain != null) rows.push([t('trackInfo.rgTrack'), `${rg.rg_track_gain.toFixed(2)} dB`])
  if (rg.rg_album_gain != null) rows.push([t('trackInfo.rgAlbum'), `${rg.rg_album_gain.toFixed(2)} dB`])
  rows.push([t('trackInfo.lyrics'), [x.lyrics.tags ? t('trackInfo.lyricsTags') : '', x.lyrics.file ? t('trackInfo.lyricsFile') : ''].filter(Boolean).join(', ') || t('trackInfo.none')])
  return rows
})
const tags = computed(() => Object.entries(info.value?.tags ?? {}).map(([k, v]) => [k, v.join(' / ')]))
</script>

<template>
  <BaseModal :title="t('trackInfo.title')" @close="emit('close')">
    <div class="flex flex-col gap-5">
      <p class="-mt-2 truncate text-[15px] font-medium">{{ track.title }}<span v-if="track.artist" class="font-light text-muted"> · {{ track.artist }}</span></p>
      <p v-if="error" class="text-[14px] text-danger" role="alert">{{ error }}</p>
      <template v-else-if="info">
        <section v-for="[title, rows] in [[t('trackInfo.fileTitle'), file], [t('trackInfo.encodingTitle'), encoding], [t('trackInfo.tagsTitle'), tags]] as [string, string[][]][]" :key="title" class="flex flex-col gap-1.5">
          <h3 class="text-[13px] font-semibold text-muted">{{ title }}</h3>
          <dl class="grid grid-cols-[minmax(84px,auto)_1fr] gap-x-4 gap-y-1.5 rounded-2xl bg-surface px-4 py-3 text-[14px]">
            <template v-for="[k, v] in rows" :key="k">
              <dt class="text-muted">{{ k }}</dt>
              <dd class="min-w-0 select-text break-all">{{ v }}</dd>
            </template>
            <p v-if="!rows.length" class="col-span-2 text-muted">{{ t('trackInfo.none') }}</p>
          </dl>
        </section>
      </template>
      <p v-else class="text-[14px] text-muted">…</p>
    </div>
  </BaseModal>
</template>
