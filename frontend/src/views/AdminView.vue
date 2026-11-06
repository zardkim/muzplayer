<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { ChartColumn, ChevronRight, FolderTree, Images, KeyRound, Library, Plus, RefreshCw, BookHeadphones, ScrollText, Users } from '@lucide/vue'
import { api } from '../api'
import { appConfig } from '../config'
import { ago, dateTime } from '../format'
import { errorMessage } from '../i18n'
import { useAuth } from '../stores/auth'
import { useUi } from '../stores/ui'
import type { FolderKind, LibraryFolder, ScanJob, User } from '../types'
import BaseModal from '../components/BaseModal.vue'
import IntegrationsCard from '../components/IntegrationsCard.vue'
import PageHeader from '../components/PageHeader.vue'
import ScanIssues from '../components/ScanIssues.vue'

// Phones: a menu of the admin parts, each on its own screen (/admin/<part>); wide screens show them all.
const props = defineProps<{ section?: string }>()
const { t } = useI18n()
const auth = useAuth()
const ui = useUi()
const menu = computed(() => [
  { key: 'library', title: 'admin.library', hint: 'admin.menu_library', icon: Library },
  { key: 'folders', title: 'admin.folders', hint: 'admin.menu_folders', icon: FolderTree },
  { key: 'photos', title: 'admin.photosTitle', hint: 'admin.menu_photos', icon: Images },
  { key: 'keys', title: 'admin.keysTitle', hint: 'admin.menu_keys', icon: KeyRound },
  ...(appConfig.audiobooks ? [{ key: 'audiobooks', title: 'admin.audiobooks', hint: 'admin.menu_audiobooks', icon: BookHeadphones }] : []),
  { key: 'users', title: 'admin.users', hint: 'admin.menu_users', icon: Users },
])
const open = computed(() => menu.value.find((x) => x.key === props.section) ?? null)
// on a phone only the open part shows (none: just the menu)
const part = (key: string) => (open.value?.key === key ? '' : 'max-md:hidden')

const job = ref<ScanJob | null>(null)
const hasMissing = ref(false)
const autoScan = ref(0)
const searchReady = ref(true) // the search index is built (search_index.py)
const users = ref<User[]>([])
const folders = ref<LibraryFolder[]>([])
const aiStatus = ref<{ provider: string; model: string; configured: boolean; banners: number; without_banner: number } | null>(null)
let poll: number | undefined

async function loadScan() {
  const r = await api<{ job: ScanJob | null; has_missing: boolean; auto_scan_minutes: number; search_index_ready: boolean }>('/admin/scan/latest')
  const wasRunning = job.value?.status === 'running'
  job.value = r.job
  hasMissing.value = r.has_missing
  autoScan.value = r.auto_scan_minutes
  searchReady.value = r.search_index_ready
  clearTimeout(poll)
  if (r.job?.status === 'running' || !r.search_index_ready) poll = window.setTimeout(loadScan, 1500)
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
  const [u, sm] = await Promise.all([api<{ items: User[] }>('/admin/users'), api<{ mode: SignupMode }>('/admin/signup')])
  // sign-ups waiting for approval first
  users.value = [...u.items].sort((a, b) => Number(!!b.pending) - Number(!!a.pending))
  signupMode.value = sm.mode
}

onMounted(() => {
  loadScan().catch((e) => ui.notify(errorMessage(e), true))
  loadUsers().catch((e) => ui.notify(errorMessage(e), true))
  loadFolders().catch((e) => ui.notify(errorMessage(e), true))
  api<NonNullable<typeof aiStatus.value>>('/admin/banners/status').then((s) => (aiStatus.value = s), () => {})
  loadBooks().catch((e) => ui.notify(errorMessage(e), true))
  loadPhotos().catch(() => {})
  usersPoll = window.setInterval(() => loadUsers().catch(() => {}), 60_000) // who is online
})
let usersPoll = 0
onUnmounted(() => {
  clearInterval(usersPoll)
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

// the search index (songs, albums, artists): built by each scan; again for everything when asked
async function rebuildSearch() {
  try {
    await api('/admin/search-index', { method: 'POST' })
    searchReady.value = false
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

// album introductions looked up after a scan: Bugs first, Melon first, or not at all
type NotesProvider = 'bugs' | 'melon' | 'off'
const notesProvider = ref<NotesProvider>('bugs')
api<{ provider: NotesProvider }>('/admin/notes-provider').then((r) => (notesProvider.value = r.provider)).catch(() => {})
async function setNotesProvider(provider: NotesProvider) {
  try {
    notesProvider.value = (await api<{ provider: NotesProvider }>('/admin/notes-provider', { method: 'PUT', body: { provider } })).provider
    ui.notify(t('admin.notesProviderSaved'))
  } catch (e) {
    ui.notify(errorMessage(e), true)
  }
}

// sign-up from the login page: off, approved by an admin, or open
type SignupMode = 'off' | 'approval' | 'open'
const signupMode = ref<SignupMode>('off')
async function setSignup(mode: SignupMode) {
  try {
    signupMode.value = (await api<{ mode: SignupMode }>('/admin/signup', { method: 'PUT', body: { mode } })).mode
    appConfig.signup = signupMode.value
    ui.notify(t('admin.signupSaved'))
  } catch (e) {
    ui.notify(errorMessage(e), true)
  }
}
const day = (iso?: string | null) => (iso ? new Date(iso).toLocaleDateString(undefined, { year: '2-digit', month: '2-digit', day: '2-digit' }) : '–')
const userFilter = ref('')
const shownUsers = computed(() => {
  const q = userFilter.value.trim().toLowerCase()
  return q ? users.value.filter((u) => `${u.display_name} ${u.username}`.toLowerCase().includes(q)) : users.value
})
const pendingCount = computed(() => users.value.filter((u) => u.pending).length)
async function removeUser(user: User) {
  if (!confirm(t(user.pending ? 'admin.rejectConfirm' : 'admin.deleteUserConfirm', { name: user.display_name }))) return
  try {
    await api(`/admin/users/${user.id}`, { method: 'DELETE' })
    ui.notify(t(user.pending ? 'admin.rejected' : 'admin.userDeleted'))
    loadUsers()
  } catch (e) {
    ui.notify(errorMessage(e), true)
  }
}
// editing a name or the admin role
const editFor = ref<User | null>(null)
const editForm = ref({ display_name: '', is_admin: false })
function openEdit(user: User) {
  editFor.value = user
  editForm.value = { display_name: user.display_name, is_admin: user.is_admin }
}
function submitEdit() {
  if (!editFor.value) return
  const body: Record<string, unknown> = { display_name: editForm.value.display_name }
  if (editFor.value.id !== auth.user?.id) body.is_admin = editForm.value.is_admin
  patch(editFor.value, body, t('admin.userSaved'))
  editFor.value = null
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
    <!-- phone: the open part's name (back goes to the menu); wide screens: Admin over everything -->
    <PageHeader v-if="open" :title="t(open.title)" :icon="open.icon" class="md:hidden" />
    <PageHeader :title="t('admin.title')" :class="open ? 'hidden md:flex' : ''">
      <template #actions>
        <RouterLink to="/admin/logs" class="hidden h-10 items-center gap-1.5 rounded-full border border-line-strong px-4 text-sm hover:border-ink md:flex"><ScrollText :size="16" :stroke-width="1.6" />{{ t('logs.title') }}</RouterLink>
        <RouterLink to="/admin/stats" class="hidden h-10 items-center gap-1.5 rounded-full border border-line-strong px-4 text-sm hover:border-ink md:flex"><ChartColumn :size="16" :stroke-width="1.6" />{{ t('stats.title') }}</RouterLink>
      </template>
    </PageHeader>

    <nav v-if="!open" :aria-label="t('admin.title')" class="-mt-3 flex flex-col md:hidden">
      <RouterLink
        v-for="x in [...menu, { key: 'logs', title: 'logs.title', hint: 'admin.menu_logs', icon: ScrollText }, { key: 'stats', title: 'stats.title', hint: 'admin.menu_stats', icon: ChartColumn }]"
        :key="x.key"
        :to="x.key === 'stats' || x.key === 'logs' ? { name: x.key } : { name: 'admin', params: { section: x.key } }"
        class="flex min-h-[64px] items-center gap-4 border-b border-surface"
      >
        <component :is="x.icon" :size="22" :stroke-width="1.4" class="flex-none text-muted" />
        <span class="flex min-w-0 flex-1 flex-col">
          <span class="text-[17px]">{{ t(x.title) }}<span v-if="x.key === 'users' && pendingCount" class="ml-2 rounded-full bg-accent px-2 py-0.5 align-middle text-xs font-medium text-white">{{ t('admin.pendingCount', { n: pendingCount }) }}</span></span>
          <span class="truncate text-[13px] font-light text-muted">{{ t(x.hint) }}</span>
        </span>
        <ChevronRight :size="18" class="flex-none text-subtle" />
      </RouterLink>
    </nav>

    <section :class="part('library')" class="flex flex-col gap-5 rounded-2xl border border-line p-5 md:p-6">
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
      <!-- every file the scans could not read, kept until the next scan of its place (again after each scan) -->
      <ScanIssues :key="`${job?.id}-${job?.status}`" />
      <label class="flex flex-wrap items-center gap-2.5 text-sm">
        {{ t('admin.notesProvider') }}
        <select :value="notesProvider" class="h-10 rounded-full border border-line-strong bg-bg px-3 text-sm" @change="setNotesProvider(($event.target as HTMLSelectElement).value as NotesProvider)">
          <option value="bugs">{{ t('admin.notesProvider_bugs') }}</option>
          <option value="melon">{{ t('admin.notesProvider_melon') }}</option>
          <option value="off">{{ t('admin.notesProvider_off') }}</option>
        </select>
      </label>
      <div class="flex flex-wrap items-center gap-x-5 gap-y-2">
        <button type="button" class="text-[13px] text-muted underline disabled:opacity-50" :disabled="job?.status === 'running'" @click="rebuildCovers">
          {{ t('admin.rebuildCovers') }}
        </button>
        <button type="button" class="text-[13px] text-muted underline disabled:opacity-50" :disabled="job?.status === 'running' || !searchReady" :title="t('admin.searchIndexHelp')" @click="rebuildSearch">
          {{ searchReady ? t('admin.searchIndex') : t('admin.searchIndexing') }}
        </button>
      </div>
    </section>

    <section :class="part('folders')" class="flex flex-col gap-4 rounded-2xl border border-line p-5 md:p-6">
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

    <section v-if="photos" :class="part('photos')" class="flex flex-col gap-3 rounded-2xl border border-line p-5 md:p-6">
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

    <IntegrationsCard :counts="aiStatus" :class="part('keys')" />

    <section v-if="appConfig.audiobooks && bookStatus" :class="part('audiobooks')" class="flex flex-col gap-5 rounded-2xl border border-line p-5 md:p-6">
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

    <section :class="part('users')" class="flex flex-col gap-4 rounded-2xl border border-line p-5 md:p-6">
      <div class="flex items-center justify-between">
        <h2 class="text-xl font-bold">{{ t('admin.users') }}<span v-if="pendingCount" class="ml-2 rounded-full bg-accent px-2 py-0.5 align-middle text-xs font-medium text-white">{{ t('admin.pendingCount', { n: pendingCount }) }}</span></h2>
        <button type="button" class="flex h-10 items-center gap-1.5 rounded-full border border-line-strong px-4 text-sm" @click="adding = true"><Plus :size="16" />{{ t('admin.addUser') }}</button>
      </div>
      <div class="flex flex-wrap items-center gap-3">
        <label class="flex items-center gap-2.5 text-sm">
          {{ t('admin.signup') }}
          <select :value="signupMode" class="h-10 rounded-full border border-line-strong bg-bg px-3 text-sm" @change="setSignup(($event.target as HTMLSelectElement).value as SignupMode)">
            <option value="off">{{ t('admin.signup_off') }}</option>
            <option value="approval">{{ t('admin.signup_approval') }}</option>
            <option value="open">{{ t('admin.signup_open') }}</option>
          </select>
        </label>
        <input v-if="users.length > 6" v-model="userFilter" type="search" :placeholder="t('admin.userSearch')" class="h-10 min-w-0 flex-1 rounded-full bg-surface px-4 text-sm outline-none focus:ring-2 focus:ring-ink sm:max-w-60" />
      </div>
      <p class="-mt-1 text-[13px] font-light text-muted">{{ t(`admin.signupHelp_${signupMode}`) }}</p>
      <!-- relative: the header's screen-reader label stays inside the scroll box (it widened the phone page) -->
      <div class="relative overflow-x-auto">
        <table class="w-full min-w-[820px] whitespace-nowrap text-sm">
          <thead>
            <tr class="border-b border-line text-left text-xs tracking-wide text-subtle">
              <th class="px-3 pb-2.5 font-medium">{{ t('admin.nameCol') }}</th>
              <th class="px-3 pb-2.5 font-medium">{{ t('admin.idCol') }}</th>
              <th class="px-3 pb-2.5 font-medium">{{ t('admin.roleCol') }}</th>
              <th class="px-3 pb-2.5 font-medium">{{ t('admin.stateCol') }}</th>
              <th class="px-3 pb-2.5 font-medium">{{ t('admin.seenCol') }}</th>
              <th class="px-3 pb-2.5 font-medium">{{ t('admin.joinedCol') }}</th>
              <th class="px-3 pb-2.5 font-medium">{{ t('admin.lastLoginCol') }}</th>
              <th class="px-3 pb-2.5"><span class="sr-only">{{ t('common.moreActions') }}</span></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(u, i) in shownUsers" :key="u.id" class="border-b border-surface" :class="u.pending ? 'bg-accent-soft/60' : ''">
              <td class="px-3 py-2.5">
                <span class="flex items-center gap-2.5">
                  <span class="relative grid size-8 flex-none place-items-center rounded-full text-[13px] font-medium text-white" :style="{ background: u.is_active ? avatarColors[i % avatarColors.length] : '#A1A1AA' }">
                    {{ u.display_name.slice(0, 1).toUpperCase() }}
                    <span v-if="u.online" class="absolute -bottom-0.5 -right-0.5 size-3 rounded-full border-2 border-bg bg-[#22c55e]" aria-hidden="true" />
                  </span>
                  {{ u.display_name }}
                </span>
              </td>
              <td class="px-3 py-2.5 text-muted">{{ u.username }}</td>
              <td class="px-3 py-2.5">
                <span class="rounded-full px-2.5 py-1 text-xs" :class="u.is_admin ? 'bg-accent-soft text-accent-strong' : 'bg-surface text-muted'">{{ u.is_admin ? t('admin.roleAdmin') : t('admin.roleUser') }}</span>
              </td>
              <td class="px-3 py-2.5" :class="u.pending ? 'font-medium text-accent-strong' : u.is_active ? '' : 'text-muted'">{{ u.pending ? t('admin.pending') : u.is_active ? t('admin.active') : t('admin.inactive') }}</td>
              <td class="px-3 py-2.5 text-[13px]" :title="u.last_seen_at ? dateTime(u.last_seen_at) : undefined">
                <span v-if="u.online" class="flex items-center gap-1.5 font-medium text-[#16a34a]"><span class="size-2 rounded-full bg-[#22c55e]" />{{ t('admin.online') }}</span>
                <span v-else class="flex items-center gap-1.5 text-muted"><span class="size-2 rounded-full bg-line-strong" />{{ u.last_seen_at ? ago(u.last_seen_at) : t('admin.offline') }}</span>
              </td>
              <td class="px-3 py-2.5 font-display text-[13px] text-muted">{{ day(u.created_at) }}</td>
              <td class="px-3 py-2.5 font-display text-[13px] text-muted" :title="u.last_login_at ? dateTime(u.last_login_at) : undefined">{{ day(u.last_login_at) }}</td>
              <td class="px-3 py-2.5">
                <span v-if="u.pending" class="flex justify-end gap-2">
                  <button type="button" class="h-9 rounded-full bg-ink px-3.5 text-[13px] text-on-ink" @click="patch(u, { is_active: true }, t('admin.approved'))">{{ t('admin.approve') }}</button>
                  <button type="button" class="h-9 rounded-full border border-line-strong px-3 text-[13px] hover:text-danger" @click="removeUser(u)">{{ t('admin.reject') }}</button>
                </span>
                <span v-else class="flex justify-end gap-2">
                  <button type="button" class="h-9 rounded-full border border-line-strong px-3 text-[13px]" @click="openEdit(u)">{{ t('admin.editUser') }}</button>
                  <button type="button" class="h-9 rounded-full border border-line-strong px-3 text-[13px]" @click="resetFor = u">{{ t('admin.resetPassword') }}</button>
                  <button
                    v-if="u.id !== auth.user?.id"
                    type="button"
                    class="h-9 rounded-full border border-line-strong px-3 text-[13px]"
                    @click="patch(u, { is_active: !u.is_active })"
                  >
                    {{ u.is_active ? t('admin.disable') : t('admin.enable') }}
                  </button>
                  <button v-if="u.id !== auth.user?.id" type="button" class="h-9 rounded-full border border-line-strong px-3 text-[13px] text-danger" @click="removeUser(u)">{{ t('admin.deleteUser') }}</button>
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

    <BaseModal v-if="editFor" :title="t('admin.editUser')" @close="editFor = null">
      <form class="flex flex-col gap-3.5" @submit.prevent="submitEdit">
        <p class="text-[13px] text-muted">{{ editFor.username }}</p>
        <label class="flex flex-col gap-1.5 text-[13px] text-muted">{{ t('admin.displayName') }}<input v-model="editForm.display_name" maxlength="100" required :class="field" /></label>
        <label v-if="editFor.id !== auth.user?.id" class="flex items-center gap-2.5 text-sm"><input v-model="editForm.is_admin" type="checkbox" class="size-4 accent-ink" />{{ t('admin.makeAdmin') }}</label>
        <button type="submit" class="h-12 rounded-full bg-ink text-on-ink">{{ t('common.save') }}</button>
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
