<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Plus, RefreshCw } from '@lucide/vue'
import { api } from '../api'
import { appConfig } from '../config'
import { dateTime } from '../format'
import { errorMessage } from '../i18n'
import { useAuth } from '../stores/auth'
import { useUi } from '../stores/ui'
import type { FolderKind, LibraryFolder, ScanJob, User } from '../types'
import BaseModal from '../components/BaseModal.vue'
import IntegrationsCard from '../components/IntegrationsCard.vue'
import PageHeader from '../components/PageHeader.vue'

const { t } = useI18n()
const auth = useAuth()
const ui = useUi()

const job = ref<ScanJob | null>(null)
const hasMissing = ref(false)
const autoScan = ref(0)
const users = ref<User[]>([])
const folders = ref<LibraryFolder[]>([])
const aiStatus = ref<{ provider: string; model: string; configured: boolean; banners: number; without_banner: number } | null>(null)
let poll: number | undefined

async function loadScan() {
  const r = await api<{ job: ScanJob | null; has_missing: boolean; auto_scan_minutes: number }>('/admin/scan/latest')
  const wasRunning = job.value?.status === 'running'
  job.value = r.job
  hasMissing.value = r.has_missing
  autoScan.value = r.auto_scan_minutes
  clearTimeout(poll)
  if (r.job?.status === 'running') poll = window.setTimeout(loadScan, 1500)
  else if (wasRunning) {
    ui.libraryCheckedAt = 0 // kept-alive lists (charts, albums) look for the new library version
    loadFolders().catch(() => {}) // track counts changed
    loadBooks().catch(() => {})
  }
}

// ---- audiobooks ----
interface ImportState {
  status: 'idle' | 'running' | 'done' | 'failed'
  total?: number
  done?: number
  books?: number
  covers?: number
  progress?: number
  failed?: string[]
  error?: string | null
}
interface BookStatus {
  folder: string
  books: number
  missing: number
  imported: number
  import: ImportState
}
interface AbsPreview {
  server_version: string
  items: number
  matched: number
  unmatched: string[]
  unmatched_count: number
  users: { id: string; username: string; suggested_user_id: number | null }[]
}
const bookStatus = ref<BookStatus | null>(null)
const abs = ref({ url: '', api_key: '' })
const absPreview = ref<AbsPreview | null>(null)
const userMap = ref<Record<string, number | ''>>({})
const absBusy = ref(false)
let importPoll: number | undefined

async function loadBooks() {
  if (!appConfig.audiobooks) return
  bookStatus.value = await api<BookStatus>('/admin/books/status')
  clearTimeout(importPoll)
  if (bookStatus.value.import.status === 'running') importPoll = window.setTimeout(() => loadBooks().catch(() => {}), 1500)
}

async function previewAbs() {
  absBusy.value = true
  try {
    absPreview.value = await api<AbsPreview>('/admin/books/abs-import/preview', { method: 'POST', body: abs.value })
    userMap.value = Object.fromEntries(absPreview.value.users.map((u) => [u.id, u.suggested_user_id ?? '']))
  } catch (e) {
    absPreview.value = null
    ui.notify(errorMessage(e), true)
  } finally {
    absBusy.value = false
  }
}

async function startImport() {
  const user_map = Object.fromEntries(Object.entries(userMap.value).filter(([, v]) => v !== ''))
  try {
    await api('/admin/books/abs-import', { method: 'POST', body: { ...abs.value, user_map } })
    // the key is needed only for this run: don't keep it on screen
    abs.value.api_key = ''
    absPreview.value = null
    await loadBooks()
  } catch (e) {
    ui.notify(errorMessage(e), true)
  }
}

async function loadFolders() {
  folders.value = (await api<{ items: LibraryFolder[] }>('/admin/folders')).items
}

const folderKinds: FolderKind[] = ['album', 'compilation', 'chart', 'theme', 'excluded']
async function setKind(folder: LibraryFolder, kind: FolderKind) {
  try {
    await api('/admin/folders', { method: 'PUT', body: { path: folder.path, kind } })
    folder.kind = kind
    // refile the folder's songs now (from stored tags: quick), so charts and themes show up
    if (job.value?.status !== 'running' && (await startScan(folder.path))) ui.notify(t('admin.folderSavedScanning'))
    else ui.notify(t('admin.folderSaved'))
  } catch (e) {
    ui.notify(errorMessage(e), true)
    loadFolders()
  }
}

// artist photos: artist.jpg in artist folders (each scan), or looked up on Wikipedia when asked
interface PhotoStatus { state: string; done?: number; found?: number; total?: number; error?: string; artists: number; with_photo: number }
const photos = ref<PhotoStatus | null>(null)
let photoPoll: number | undefined
async function loadPhotos() {
  photos.value = await api<PhotoStatus>('/admin/artist-images/status')
  clearTimeout(photoPoll)
  if (photos.value.state === 'running') photoPoll = window.setTimeout(() => loadPhotos().catch(() => {}), 2000)
  else if (photos.value.state === 'done') ui.libraryCheckedAt = 0
}
async function findPhotos() {
  try {
    await api('/admin/artist-images/lookup', { method: 'POST' })
    loadPhotos()
  } catch (e) {
    ui.notify(errorMessage(e), true)
  }
}

async function loadUsers() {
  users.value = (await api<{ items: User[] }>('/admin/users')).items
}

onMounted(() => {
  loadScan().catch((e) => ui.notify(errorMessage(e), true))
  loadUsers().catch((e) => ui.notify(errorMessage(e), true))
  loadFolders().catch((e) => ui.notify(errorMessage(e), true))
  api<NonNullable<typeof aiStatus.value>>('/admin/banners/status').then((s) => (aiStatus.value = s), () => {})
  loadBooks().catch((e) => ui.notify(errorMessage(e), true))
  loadPhotos().catch(() => {})
})
onUnmounted(() => {
  clearTimeout(poll)
  clearTimeout(photoPoll)
  clearTimeout(importPoll)
})

// the whole library, or one top-level folder: scan (new and changed files), rescan (every
// file's tags again, songs keep their stars and plays) or reset (songs forgotten and read again)
async function startScan(folder?: string, mode: 'scan' | 'rescan' | 'reset' = 'scan') {
  try {
    job.value = await api<ScanJob>('/admin/scan', { method: 'POST', body: folder ? { folder, mode } : {} })
    poll = window.setTimeout(loadScan, 1000)
    return true
  } catch (e) {
    ui.notify(errorMessage(e), true)
    return false
  }
}

async function resetFolder(f: LibraryFolder) {
  try {
    const n = await api<{ tracks: number; ratings: number; favorites: number; playlist_entries: number; play_counts: number }>(
      `/admin/folders/impact?path=${encodeURIComponent(f.path)}`,
    )
    if (!confirm(t('admin.resetConfirm', { folder: f.path, tracks: n.tracks, ratings: n.ratings, favorites: n.favorites, playlists: n.playlist_entries, plays: n.play_counts }))) return
    startScan(f.path, 'reset')
  } catch (e) {
    ui.notify(errorMessage(e), true)
  }
}

const stopping = ref(false)
async function stopScan() {
  stopping.value = true
  try {
    await api('/admin/scan/cancel', { method: 'POST' })
  } catch (e) {
    ui.notify(errorMessage(e), true)
  }
}
watch(() => job.value?.status, (s) => s !== 'running' && (stopping.value = false))

// how long the last scan took (to judge auto-scan intervals on a big library)
function took(j: ScanJob) {
  if (!j.finished_at) return ''
  const sec = Math.max(0, Math.round((new Date(j.finished_at).getTime() - new Date(j.started_at).getTime()) / 1000))
  return t('admin.scanTook', { time: t('admin.minSec', { m: Math.floor(sec / 60), s: sec % 60 }) })
}

async function rebuildCovers() {
  if (!confirm(t('admin.rebuildCoversConfirm'))) return
  try {
    job.value = await api<ScanJob>('/admin/covers/rebuild', { method: 'POST' })
    ui.notify(t('admin.rebuildCoversStarted'))
    poll = window.setTimeout(loadScan, 1000)
  } catch (e) {
    ui.notify(errorMessage(e), true)
  }
}

async function purge() {
  if (!confirm(t('admin.purgeConfirm'))) return
  try {
    const r = await api<{ deleted: number }>('/admin/missing-tracks?days=30', { method: 'DELETE' })
    ui.notify(t('admin.purged', { n: r.deleted }))
    loadScan()
  } catch (e) {
    ui.notify(errorMessage(e), true)
  }
}

// ---- users ----
const adding = ref(false)
const form = ref({ username: '', display_name: '', password: '', is_admin: false })
const formError = ref('')
async function addUser() {
  formError.value = ''
  try {
    await api('/admin/users', { method: 'POST', body: form.value })
    adding.value = false
    form.value = { username: '', display_name: '', password: '', is_admin: false }
    loadUsers()
  } catch (e) {
    formError.value = errorMessage(e)
  }
}

async function patch(user: User, body: Record<string, unknown>, done?: string) {
  try {
    await api(`/admin/users/${user.id}`, { method: 'PATCH', body })
    if (done) ui.notify(done)
    loadUsers()
  } catch (e) {
    ui.notify(errorMessage(e), true)
  }
}

const resetFor = ref<User | null>(null)
const resetPassword = ref('')
function submitReset() {
  if (!resetFor.value || resetPassword.value.length < 8) return
  patch(resetFor.value, { password: resetPassword.value }, t('admin.passwordReset'))
  resetFor.value = null
  resetPassword.value = ''
}

const avatarColors = ['#3D5A80', '#2F7D6D', '#6B5B95', '#8A6516', '#A34A6E']
const field = 'h-12 rounded-full bg-surface px-4 text-base text-ink outline-none focus:ring-2 focus:ring-ink'
const cardField = field.replace('bg-surface', 'bg-bg') // inputs on the grey import panel
</script>

<template>
  <div class="flex flex-col gap-7">
    <PageHeader :title="t('admin.title')" />

    <section class="flex flex-col gap-5 rounded-2xl border border-line p-5 md:p-6">
      <div class="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 class="text-xl font-bold">{{ t('admin.library') }}</h2>
          <p class="mt-1 text-sm font-light text-muted">{{ t('admin.libraryDesc') }}</p>
          <p class="mt-1 text-[13px] text-muted">{{ autoScan > 0 ? t('admin.autoScan', { n: autoScan }) : t('admin.autoScanOff') }}</p>
        </div>
        <div class="flex flex-wrap gap-2.5">
          <button v-if="hasMissing" type="button" class="h-11 rounded-full border border-line-strong px-4 text-sm" @click="purge">{{ t('admin.purge') }}</button>
          <button v-if="job?.status === 'running'" type="button" class="h-11 rounded-full border border-line-strong px-4 text-sm disabled:opacity-50" :disabled="stopping" @click="stopScan">
            {{ stopping ? t('admin.stoppingScan') : t('admin.stopScan') }}
          </button>
          <button
            type="button"
            class="flex h-11 items-center gap-2 rounded-full bg-ink px-5 text-sm text-on-ink disabled:opacity-50"
            :disabled="job?.status === 'running'"
            @click="startScan()"
          >
            <RefreshCw :size="18" :class="job?.status === 'running' ? 'animate-spin' : ''" />{{ t('admin.startScan') }}
          </button>
        </div>
      </div>

      <div v-if="job?.status === 'running'" class="flex flex-col gap-2">
        <div class="text-[13px] text-muted"><template v-if="job.folder">{{ t(`admin.scanScope_${job.mode}`, { folder: job.folder }) }} · </template>{{ t('admin.scanning', { n: job.scanned }) }}</div>
        <div class="h-1.5 overflow-hidden rounded-full bg-line"><div class="h-1.5 w-2/5 animate-pulse rounded-full bg-accent" /></div>
      </div>
      <p v-else-if="job" class="text-[13px]" :class="job.status === 'failed' ? 'text-danger' : 'text-muted'">
        <template v-if="job.status === 'failed' && job.error_summary === 'interrupted'">{{ t('admin.scanInterrupted') }} · </template>
        <template v-else-if="job.status === 'failed'">{{ t('admin.scanFailed') }} · </template>
        <template v-else-if="job.status === 'cancelled'">{{ t('admin.scanCancelled') }} · </template><template v-if="job.folder">{{ t(`admin.scanScope_${job.mode}`, { folder: job.folder }) }} · </template>{{ t('admin.lastScan', { time: dateTime(job.finished_at ?? job.started_at) }) }}<template v-if="took(job)"> · {{ took(job) }}</template>
      </p>
      <p v-else class="text-[13px] text-muted">{{ t('admin.neverScanned') }}</p>
      <p v-if="job?.status === 'failed' && /^(music_dir_not_found|library_empty)/.test(job.error_summary ?? '')" class="text-[13px] leading-relaxed text-danger">
        {{ t('admin.noLibrary') }}
      </p>

      <div v-if="job" class="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div class="flex flex-col gap-1 rounded-xl bg-surface px-4 py-3.5"><span class="text-[13px] text-muted">{{ t('admin.added') }}</span><span class="font-display text-[22px] font-bold">{{ job.added }}</span></div>
        <div class="flex flex-col gap-1 rounded-xl bg-surface px-4 py-3.5"><span class="text-[13px] text-muted">{{ t('admin.updated') }}</span><span class="font-display text-[22px] font-bold">{{ job.updated }}</span></div>
        <div class="flex flex-col gap-1 rounded-xl bg-surface px-4 py-3.5"><span class="text-[13px] text-muted">{{ t('admin.missing') }}</span><span class="font-display text-[22px] font-bold text-accent">{{ job.missing }}</span></div>
        <div class="flex flex-col gap-1 rounded-xl bg-surface px-4 py-3.5"><span class="text-[13px] text-muted">{{ t('admin.errors') }}</span><span class="font-display text-[22px] font-bold text-danger">{{ job.errors }}</span></div>
      </div>
      <p v-if="job && appConfig.audiobooks && job.status !== 'running'" class="text-[13px] text-muted">
        {{ t('admin.bookScanResult', { added: job.books_added, updated: job.books_updated, missing: job.books_missing }) }}
      </p>
      <details v-if="job?.error_summary" class="text-[13px] text-muted">
        <summary class="cursor-pointer">{{ t('admin.errorDetails') }}</summary>
        <pre class="mt-2 max-h-60 overflow-auto whitespace-pre-wrap rounded-xl bg-surface p-3 text-xs">{{ job.error_summary }}</pre>
      </details>
      <button type="button" class="self-start text-[13px] text-muted underline disabled:opacity-50" :disabled="job?.status === 'running'" @click="rebuildCovers">
        {{ t('admin.rebuildCovers') }}
      </button>
    </section>

    <section class="flex flex-col gap-4 rounded-2xl border border-line p-5 md:p-6">
      <div>
        <h2 class="text-xl font-bold">{{ t('admin.folders') }}</h2>
        <p class="mt-1 text-sm font-light text-muted">{{ t('admin.foldersDesc') }}</p>
      </div>
      <p v-if="!folders.length" class="text-sm text-muted">{{ t('admin.noFolders') }}</p>
      <ul v-else class="flex flex-col">
        <li v-for="f in folders" :key="f.path" class="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-surface py-3 last:border-0">
          <span class="flex min-w-0 flex-1 flex-col">
            <span class="truncate text-[15px]" :class="f.present ? '' : 'text-muted line-through'">{{ f.path }}</span>
            <span class="text-[13px] text-muted">
              <template v-if="f.audiobooks">{{ t('admin.audiobookFolder') }}</template>
              <template v-else>{{ f.present ? t('common.tracks', f.track_count) : t('admin.folderMissing') }}</template>
              <template v-if="!f.audiobooks && f.suggested && f.suggested !== f.kind">
                · {{ t('admin.suggested', { kind: t(`admin.folderKind_${f.suggested}`) }) }}
                <button type="button" class="ml-1 text-accent underline" @click="setKind(f, f.suggested)">{{ t('admin.applySuggestion') }}</button>
              </template>
            </span>
          </span>
          <label v-if="!f.audiobooks" class="sr-only" :for="`kind-${f.path}`">{{ t('admin.kindCol') }}</label>
          <select
            v-if="!f.audiobooks"
            :id="`kind-${f.path}`"
            class="h-10 rounded-full border border-line-strong bg-bg px-3 text-sm"
            :value="f.kind"
            @change="setKind(f, ($event.target as HTMLSelectElement).value as FolderKind)"
          >
            <option v-for="k in folderKinds" :key="k" :value="k">{{ t(`admin.folderKind_${k}`) }}</option>
          </select>
          <div v-if="!f.audiobooks && f.present" class="flex gap-1.5" role="group" :aria-label="f.path">
            <button type="button" class="h-9 rounded-full border border-line-strong px-3 text-[13px] hover:bg-surface disabled:opacity-40" :disabled="job?.status === 'running'" :title="t('admin.folderScanHelp')" @click="startScan(f.path, 'scan')">{{ t('admin.folderScan') }}</button>
            <button type="button" class="h-9 rounded-full border border-line-strong px-3 text-[13px] hover:bg-surface disabled:opacity-40" :disabled="job?.status === 'running'" :title="t('admin.folderRescanHelp')" @click="startScan(f.path, 'rescan')">{{ t('admin.folderRescan') }}</button>
            <button type="button" class="h-9 rounded-full border border-danger/40 px-3 text-[13px] text-danger hover:bg-danger/5 disabled:opacity-40" :disabled="job?.status === 'running'" :title="t('admin.folderResetHelp')" @click="resetFolder(f)">{{ t('admin.folderReset') }}</button>
          </div>
        </li>
      </ul>
      <p class="text-[13px] leading-relaxed text-muted">{{ t('admin.foldersHelp') }}</p>
    </section>

    <section v-if="photos" class="flex flex-col gap-3 rounded-2xl border border-line p-5 md:p-6">
      <div class="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 class="text-xl font-bold">{{ t('admin.photosTitle') }}</h2>
          <p class="mt-1 text-sm font-light text-muted">{{ t('admin.photosDesc') }}</p>
        </div>
        <button type="button" class="h-11 rounded-full bg-ink px-5 text-sm text-on-ink disabled:opacity-50" :disabled="photos.state === 'running'" @click="findPhotos">
          {{ photos.state === 'running' ? t('admin.photosRunning', { done: photos.done ?? 0, total: photos.total ?? 0 }) : t('admin.photosFind') }}
        </button>
      </div>
      <p class="text-[13px] text-muted">
        {{ t('admin.photosCount', { n: photos.with_photo, total: photos.artists }) }}
        <template v-if="photos.state === 'done'"> · {{ t('admin.photosDone', { found: photos.found ?? 0, total: photos.total ?? 0 }) }}</template>
      </p>
      <p v-if="photos.state === 'failed'" class="text-[13px] text-danger">{{ t('admin.photosFailed') }}</p>
    </section>

    <IntegrationsCard :counts="aiStatus" />

    <section v-if="appConfig.audiobooks && bookStatus" class="flex flex-col gap-5 rounded-2xl border border-line p-5 md:p-6">
      <div>
        <h2 class="text-xl font-bold">{{ t('admin.audiobooks') }}</h2>
        <p class="mt-1 break-all text-sm font-light text-muted">{{ t('admin.audiobooksFolder', { folder: bookStatus.folder }) }}</p>
        <p class="mt-1 text-[13px] text-muted">
          {{ t('admin.booksCount', { n: bookStatus.books }) }} · {{ t('admin.booksImported', { n: bookStatus.imported }) }}<template v-if="bookStatus.missing"> · {{ t('admin.booksMissing', { n: bookStatus.missing }) }}</template>
        </p>
      </div>

      <div class="flex flex-col gap-3 rounded-xl bg-surface p-4">
        <h3 class="font-medium">{{ t('admin.absTitle') }}</h3>
        <p class="text-[13px] leading-relaxed text-muted">{{ t('admin.absDesc') }}</p>

        <template v-if="bookStatus.import.status === 'running'">
          <p class="text-[14px]">{{ t('admin.absRunning', { done: bookStatus.import.done ?? 0, total: bookStatus.import.total ?? 0 }) }}</p>
          <div class="h-1.5 overflow-hidden rounded-full bg-line"><div class="h-1.5 w-2/5 animate-pulse rounded-full bg-accent" /></div>
        </template>
        <template v-else>
          <p v-if="bookStatus.import.status === 'done'" class="text-[14px] text-ink">
            {{ t('admin.absDone', { books: bookStatus.import.books ?? 0, covers: bookStatus.import.covers ?? 0, progress: bookStatus.import.progress ?? 0 }) }}
          </p>
          <p v-else-if="bookStatus.import.status === 'failed'" class="text-[14px] text-danger">{{ t('admin.absFailed') }} {{ errorMessage({ code: bookStatus.import.error }) }}</p>
          <details v-if="bookStatus.import.failed?.length" class="text-[13px] text-muted">
            <summary class="cursor-pointer">{{ t('admin.absFailedItems', { n: bookStatus.import.failed.length }) }}</summary>
            <pre class="mt-2 max-h-48 overflow-auto whitespace-pre-wrap text-xs">{{ bookStatus.import.failed.join('\n') }}</pre>
          </details>

          <form class="flex flex-col gap-3" @submit.prevent="previewAbs">
            <label class="flex flex-col gap-1.5 text-[13px] text-muted">{{ t('admin.absUrl') }}<input v-model.trim="abs.url" type="url" required placeholder="http://192.168.0.10:13378" autocapitalize="none" :class="cardField" /></label>
            <label class="flex flex-col gap-1.5 text-[13px] text-muted">
              {{ t('admin.absKey') }}
              <input v-model.trim="abs.api_key" type="password" required autocomplete="off" :class="cardField" />
              <span class="text-[12px] leading-relaxed">{{ t('admin.absKeyHelp') }}</span>
            </label>
            <button type="submit" class="h-11 self-start rounded-full border border-ink px-5 text-sm disabled:opacity-50" :disabled="absBusy">{{ absBusy ? t('common.loading') : t('admin.absPreview') }}</button>
          </form>

          <div v-if="absPreview" class="flex flex-col gap-3 border-t border-line pt-3">
            <p class="text-[14px]">{{ t('admin.absMatched', { matched: absPreview.matched, items: absPreview.items, version: absPreview.server_version }) }}</p>
            <details v-if="absPreview.unmatched_count" class="text-[13px] text-muted">
              <summary class="cursor-pointer text-danger">{{ t('admin.absUnmatched', { n: absPreview.unmatched_count }) }}</summary>
              <p class="mt-1">{{ t('admin.absUnmatchedHelp') }}</p>
              <pre class="mt-2 max-h-48 overflow-auto whitespace-pre-wrap text-xs">{{ absPreview.unmatched.join('\n') }}</pre>
            </details>
            <h4 class="mt-1 text-[14px] font-medium">{{ t('admin.absUsers') }}</h4>
            <p class="text-[13px] text-muted">{{ t('admin.absUsersHelp') }}</p>
            <div v-for="u in absPreview.users" :key="u.id" class="flex items-center justify-between gap-3">
              <span class="truncate text-[15px]">{{ u.username }}</span>
              <select v-model="userMap[u.id]" class="h-10 rounded-full border border-line-strong bg-bg px-3 text-sm" :aria-label="t('admin.absUserFor', { name: u.username })">
                <option value="">{{ t('admin.absUserSkip') }}</option>
                <option v-for="m in users" :key="m.id" :value="m.id">{{ m.display_name }} ({{ m.username }})</option>
              </select>
            </div>
            <button type="button" class="h-11 self-start rounded-full bg-ink px-5 text-sm text-on-ink disabled:opacity-50" :disabled="!absPreview.matched || job?.status === 'running'" @click="startImport">
              {{ t('admin.absStart', { n: absPreview.matched }) }}
            </button>
          </div>
        </template>
      </div>
    </section>

    <section class="flex flex-col gap-4 rounded-2xl border border-line p-5 md:p-6">
      <div class="flex items-center justify-between">
        <h2 class="text-xl font-bold">{{ t('admin.users') }}</h2>
        <button type="button" class="flex h-10 items-center gap-1.5 rounded-full border border-line-strong px-4 text-sm" @click="adding = true"><Plus :size="16" />{{ t('admin.addUser') }}</button>
      </div>
      <div class="overflow-x-auto">
        <table class="w-full min-w-[640px] text-sm">
          <thead>
            <tr class="border-b border-line text-left text-xs tracking-wide text-subtle">
              <th class="px-3 pb-2.5 font-medium">{{ t('admin.nameCol') }}</th>
              <th class="px-3 pb-2.5 font-medium">{{ t('admin.idCol') }}</th>
              <th class="px-3 pb-2.5 font-medium">{{ t('admin.roleCol') }}</th>
              <th class="px-3 pb-2.5 font-medium">{{ t('admin.stateCol') }}</th>
              <th class="px-3 pb-2.5"><span class="sr-only">{{ t('common.moreActions') }}</span></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(u, i) in users" :key="u.id" class="border-b border-surface">
              <td class="px-3 py-2.5">
                <span class="flex items-center gap-2.5">
                  <span class="grid size-8 place-items-center rounded-full text-[13px] font-medium text-white" :style="{ background: u.is_active ? avatarColors[i % avatarColors.length] : '#A1A1AA' }">{{ u.display_name.slice(0, 1).toUpperCase() }}</span>
                  {{ u.display_name }}
                </span>
              </td>
              <td class="px-3 py-2.5 text-muted">{{ u.username }}</td>
              <td class="px-3 py-2.5">
                <span class="rounded-full px-2.5 py-1 text-xs" :class="u.is_admin ? 'bg-accent-soft text-accent-strong' : 'bg-surface text-muted'">{{ u.is_admin ? t('admin.roleAdmin') : t('admin.roleUser') }}</span>
              </td>
              <td class="px-3 py-2.5" :class="u.is_active ? '' : 'text-muted'">{{ u.is_active ? t('admin.active') : t('admin.inactive') }}</td>
              <td class="px-3 py-2.5">
                <span class="flex justify-end gap-2">
                  <button type="button" class="h-9 rounded-full border border-line-strong px-3 text-[13px]" @click="resetFor = u">{{ t('admin.resetPassword') }}</button>
                  <button
                    v-if="u.id !== auth.user?.id"
                    type="button"
                    class="h-9 rounded-full border border-line-strong px-3 text-[13px]"
                    @click="patch(u, { is_active: !u.is_active })"
                  >
                    {{ u.is_active ? t('admin.disable') : t('admin.enable') }}
                  </button>
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <BaseModal v-if="adding" :title="t('admin.addUser')" @close="adding = false">
      <form class="flex flex-col gap-3.5" @submit.prevent="addUser">
        <label class="flex flex-col gap-1.5 text-[13px] text-muted">{{ t('admin.username') }}<input v-model="form.username" required pattern="[A-Za-z0-9._\-]+" maxlength="64" autocapitalize="none" :class="field" /></label>
        <label class="flex flex-col gap-1.5 text-[13px] text-muted">{{ t('admin.displayName') }}<input v-model="form.display_name" maxlength="100" :class="field" /></label>
        <label class="flex flex-col gap-1.5 text-[13px] text-muted">{{ t('admin.password') }}<input v-model="form.password" type="password" autocomplete="new-password" required minlength="8" :class="field" /></label>
        <label class="flex items-center gap-2.5 text-sm"><input v-model="form.is_admin" type="checkbox" class="size-4 accent-ink" />{{ t('admin.makeAdmin') }}</label>
        <p v-if="formError" role="alert" class="text-[13px] text-danger">{{ formError }}</p>
        <button type="submit" class="mt-1 h-12 rounded-full bg-ink text-on-ink">{{ t('common.create') }}</button>
      </form>
    </BaseModal>

    <BaseModal v-if="resetFor" :title="t('admin.resetPassword')" @close="resetFor = null">
      <form class="flex flex-col gap-3.5" @submit.prevent="submitReset">
        <label class="flex flex-col gap-1.5 text-[13px] text-muted">
          {{ t('admin.resetPasswordFor', { name: resetFor.display_name }) }}
          <input v-model="resetPassword" type="password" autocomplete="new-password" required minlength="8" :class="field" />
        </label>
        <button type="submit" class="h-12 rounded-full bg-ink text-on-ink">{{ t('common.save') }}</button>
      </form>
    </BaseModal>
  </div>
</template>
