<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { CircleAlert, Music, RotateCcw, Tag, Trash2, X } from '@lucide/vue'
import { api } from '../api'
import { errorMessage } from '../i18n'
import { useUi } from '../stores/ui'
import BaseModal from './BaseModal.vue'
import CoverArt from './CoverArt.vue'
import ExtractTagSheet from './ExtractTagSheet.vue'

// Admin: the songs taken out of music videos (backend extract.py) — each job's state, the tags it
// wrote, the album it went into — and the settings: YouTube on or off (its terms), the format.
const emit = defineEmits<{ close: [] }>()
const { t } = useI18n()
const ui = useUi()
interface Job {
  id: number; title: string; format: string; status: 'pending' | 'running' | 'done' | 'failed'; step: string; progress: number
  error: string | null
  found: {
    title: string; artist: string; album: string; source: string; cover: string | null
    review?: string[]; bugs?: { track: string; album: string | null }; lyrics_from?: string | null; original?: { artist: string; title: string }; edited?: boolean
  } | null
  file_path: string | null; track_id: number | null; album_id: number | null; has_cover: boolean; cover_v: number
}
interface Status {
  folder: string; folder_ok: boolean; ytdlp: string | null; deno: boolean; ffmpeg: boolean; youtube: boolean; format: 'm4a' | 'mp3'; ai: boolean; ai_ready: boolean
  ytdlp_update: { state: 'idle' | 'running' | 'done' | 'failed'; error: string | null; custom: boolean }
}
const jobs = ref<Job[]>([])
const status = ref<Status | null>(null)
let timer = 0
async function load() {
  const r = await api<{ items: Job[]; running: boolean }>('/extract/jobs')
  jobs.value = r.items
  window.clearTimeout(timer)
  if (r.running) timer = window.setTimeout(() => void load().catch(() => {}), 2000)
}
onMounted(() => {
  load().catch((e) => ui.notify(errorMessage(e), true))
  api<Status>('/extract/status').then((s) => (status.value = s), () => {})
})
onUnmounted(() => window.clearTimeout(timer))

async function setting(body: { youtube?: boolean; format?: string; ai?: boolean }) {
  if (body.youtube && !confirm(t('extract.youtubeConfirm'))) return
  status.value = await api<Status>('/extract/settings', { method: 'PUT', body }).catch((e) => (ui.notify(errorMessage(e), true), status.value))
}
async function retry(j: Job) {
  await api(`/extract/jobs/${j.id}/retry`, { method: 'POST' }).catch((e) => ui.notify(errorMessage(e), true))
  await load()
}
async function remove(j: Job, file: boolean) {
  if (file && !confirm(t('extract.deleteFileConfirm', { name: j.found?.title ?? j.title }))) return
  await api(`/extract/jobs/${j.id}?file=${file}`, { method: 'DELETE' }).catch((e) => ui.notify(errorMessage(e), true))
  await load()
}
const stateText = (j: Job) =>
  j.status === 'running' ? t(`extract.step_${j.step || 'download'}`) + (j.step === 'download' && j.progress ? ` ${Math.round(j.progress * 100)}%` : '') : t(`extract.status_${j.status}`)
const errorText = (code: string | null) => (code ? errorMessage({ code }) : '')
// where the tags came from (the AI or the title, confirmed on Bugs), the lyrics, and what to check
const sources = (j: Job) => {
  const f = j.found
  if (!f) return ''
  return [f.edited ? t('extract.edited') : '', f.original ? t('extract.coverOf', { artist: f.original.artist }) : '', t(`extract.from_${f.source}`), f.bugs ? t('extract.fromBugs') : '', f.lyrics_from ? t('extract.lyrics') : ''].filter(Boolean).join(' · ')
}
const review = (j: Job) => (j.found?.review ?? []).map((r) => t(`extract.review_${r}`)).join(' · ')
// a newer yt-dlp (installed on the server beside the image's), or back to the image's
let statusTimer = 0
async function followUpdate() {
  window.clearTimeout(statusTimer)
  status.value = await api<Status>('/extract/status').catch(() => status.value)
  if (status.value?.ytdlp_update.state === 'running') statusTimer = window.setTimeout(() => void followUpdate(), 2000)
  else if (status.value?.ytdlp_update.state === 'failed') ui.notify(errorMessage({ code: status.value.ytdlp_update.error ?? 'extract_update_failed' }), true)
}
async function updateYtdlp() {
  await api('/extract/ytdlp', { method: 'POST' }).catch((e) => ui.notify(errorMessage(e), true))
  await followUpdate()
}
async function resetYtdlp() {
  if (!confirm(t('extract.ytdlpResetConfirm'))) return
  status.value = await api<Status>('/extract/ytdlp', { method: 'DELETE' }).then(() => api<Status>('/extract/status')).catch((e) => (ui.notify(errorMessage(e), true), status.value))
}
onUnmounted(() => window.clearTimeout(statusTimer))
// a finished song's tags (ExtractTagSheet)
const editing = ref<Job | null>(null)
const active = computed(() => jobs.value.filter((j) => j.status === 'pending' || j.status === 'running').length)
</script>

<template>
  <BaseModal wide :title="t('extract.jobsTitle')" @close="emit('close')">
    <div class="flex flex-col gap-5">
      <!-- settings -->
      <section v-if="status" class="flex flex-col gap-2 rounded-2xl bg-surface p-3.5 text-[14px]">
        <label class="flex items-start gap-2.5">
          <input type="checkbox" :checked="status.youtube" class="mt-0.5 size-4 accent-accent" @change="setting({ youtube: ($event.target as HTMLInputElement).checked })" />
          <span>{{ t('extract.youtubeOn') }}<span class="block text-[12px] font-light text-muted">{{ t('extract.youtubeHelp') }}</span></span>
        </label>
        <label class="flex items-start gap-2.5" :class="status.ai_ready ? '' : 'opacity-60'">
          <input type="checkbox" :checked="status.ai && status.ai_ready" :disabled="!status.ai_ready" class="mt-0.5 size-4 accent-accent" @change="setting({ ai: ($event.target as HTMLInputElement).checked })" />
          <span>{{ t('extract.aiOn') }}<span class="block text-[12px] font-light text-muted">{{ status.ai_ready ? t('extract.aiHelp') : t('extract.aiNoKey') }}</span></span>
        </label>
        <label class="flex items-center gap-2.5">
          <span class="flex-1">{{ t('extract.defaultFormat') }}</span>
          <select :value="status.format" class="h-9 rounded-full border border-line-strong bg-bg px-3 text-[14px]" @change="setting({ format: ($event.target as HTMLSelectElement).value })">
            <option value="m4a">m4a</option><option value="mp3">mp3</option>
          </select>
        </label>
        <p class="text-[12px] text-muted">
          <span :class="status.folder_ok ? '' : 'text-danger'">{{ status.folder_ok ? t('extract.folderOk', { folder: status.folder }) : t('extract.noFolder') }}</span>
          · yt-dlp {{ status.ytdlp ?? '—' }}{{ status.ytdlp_update.custom ? ` (${t('extract.ytdlpCustom')})` : '' }}{{ status.deno ? '' : ` · ${t('extract.noDeno')}` }}
        </p>
        <div class="flex flex-wrap items-center gap-2">
          <button type="button" class="h-9 rounded-full border border-line-strong bg-bg px-3.5 text-[13px] hover:border-ink disabled:opacity-50" :disabled="status.ytdlp_update.state === 'running'" @click="updateYtdlp">
            {{ status.ytdlp_update.state === 'running' ? t('extract.ytdlpUpdating') : t('extract.ytdlpUpdate') }}
          </button>
          <button v-if="status.ytdlp_update.custom && status.ytdlp_update.state !== 'running'" type="button" class="text-[13px] text-muted underline hover:text-ink" @click="resetYtdlp">{{ t('extract.ytdlpReset') }}</button>
          <span v-if="status.ytdlp_update.state === 'done'" class="text-[13px] text-accent">{{ t('extract.ytdlpUpdated', { v: status.ytdlp }) }}</span>
        </div>
      </section>

      <h3 class="font-medium">{{ t('extract.jobs') }}<span v-if="active" class="ml-1.5 text-[13px] text-accent">{{ t('extract.active', { n: active }) }}</span></h3>
      <p v-if="!jobs.length" class="text-[14px] font-light text-muted">{{ t('extract.none') }}</p>
      <ul class="flex flex-col">
        <li v-for="j in jobs" :key="j.id" class="flex items-center gap-3 border-b border-line py-2.5 last:border-0">
          <RouterLink v-if="j.album_id" :to="{ name: 'album', params: { id: j.album_id } }" class="size-12 flex-none" @click="emit('close')">
            <CoverArt :album-id="j.album_id" :has-cover="j.has_cover" :version="j.cover_v" rounded="rounded-lg" />
          </RouterLink>
          <span v-else class="grid size-12 flex-none place-items-center rounded-lg bg-surface text-muted"><Music :size="20" :stroke-width="1.4" /></span>
          <span class="flex min-w-0 flex-1 flex-col gap-0.5">
            <span class="truncate text-[15px]">{{ j.found ? [j.found.title, j.found.artist].filter(Boolean).join(' · ') : j.title }}</span>
            <span class="truncate text-[12px] text-muted">{{ j.format.toUpperCase() }} · {{ j.found?.album || j.title }}<template v-if="sources(j)"> · {{ sources(j) }}</template></span>
            <span v-if="review(j)" class="flex items-center gap-1 text-[12px] text-danger"><CircleAlert :size="13" :stroke-width="1.8" />{{ t('extract.review') }}: {{ review(j) }}</span>
            <span class="text-[12px]" :class="j.status === 'failed' ? 'text-danger' : j.status === 'done' ? 'text-accent' : 'text-muted'">
              {{ stateText(j) }}<template v-if="j.error"> · {{ errorText(j.error) }}</template>
            </span>
            <span v-if="j.status === 'running' && j.step === 'download'" class="mt-0.5 h-1 rounded-full bg-surface"><span class="block h-full rounded-full bg-accent transition-[width]" :style="{ width: `${Math.round(j.progress * 100)}%` }" /></span>
          </span>
          <button v-if="j.status === 'failed'" type="button" class="grid size-9 flex-none place-items-center rounded-full text-muted hover:bg-surface hover:text-ink" :aria-label="t('extract.retry')" :title="t('extract.retry')" @click="retry(j)"><RotateCcw :size="17" :stroke-width="1.7" /></button>
          <button v-if="j.status === 'done' && j.track_id" type="button" class="grid size-9 flex-none place-items-center rounded-full text-muted hover:bg-surface hover:text-ink" :aria-label="t('extractTags.edit')" :title="t('extractTags.edit')" @click="editing = j"><Tag :size="17" :stroke-width="1.7" /></button>
          <button v-if="j.status === 'done' && j.file_path" type="button" class="grid size-9 flex-none place-items-center rounded-full text-muted hover:bg-surface hover:text-danger" :aria-label="t('extract.deleteFile')" :title="t('extract.deleteFile')" @click="remove(j, true)"><Trash2 :size="17" :stroke-width="1.7" /></button>
          <button v-if="j.status !== 'running'" type="button" class="grid size-9 flex-none place-items-center rounded-full text-muted hover:bg-surface hover:text-ink" :aria-label="t('extract.forget')" :title="t('extract.forget')" @click="remove(j, false)"><X :size="17" :stroke-width="1.7" /></button>
        </li>
      </ul>
    </div>
    <ExtractTagSheet v-if="editing && editing.track_id" :tracks="[{ id: editing.track_id, title: editing.found?.title ?? editing.title }]" @close="editing = null" @saved="load" />
  </BaseModal>
</template>
