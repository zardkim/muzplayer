<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { Download, RotateCcw, Trash2, Upload } from '@lucide/vue'
import { api, ApiError } from '../api'
import { dateTime } from '../format'
import { errorMessage } from '../i18n'
import { useUi } from '../stores/ui'

// Admin: backups of the settings and the database (backend backup.py), kept on the server (the last
// few) and downloaded; a restore replaces both, from a kept one or a file, and signs everyone out.
const { t } = useI18n()
const ui = useUi()
interface Backup { name: string; size: number; created: string }
const items = ref<Backup[]>([])
const keep = ref(5)
const busy = ref<'' | 'backup' | 'restore'>('')
const file = ref<HTMLInputElement | null>(null)

async function load() {
  const r = await api<{ items: Backup[]; keep: number }>('/admin/backups')
  items.value = r.items
  keep.value = r.keep
}
onMounted(() => load().catch(() => {}))

const size = (n: number) => (n >= 1 << 20 ? `${(n / (1 << 20)).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`)

async function backupNow() {
  busy.value = 'backup'
  try {
    await api('/admin/backups', { method: 'POST' })
    await load()
    ui.notify(t('backup.made'))
  } catch (e) {
    ui.notify(errorMessage(e), true)
  } finally {
    busy.value = ''
  }
}

async function remove(b: Backup) {
  if (!confirm(t('backup.deleteConfirm', { name: b.name }))) return
  await api(`/admin/backups/${encodeURIComponent(b.name)}`, { method: 'DELETE' }).catch((e) => ui.notify(errorMessage(e), true))
  await load()
}

interface RestoreStatus { state: 'idle' | 'running' | 'done' | 'failed'; error?: string; created?: string; covers_missing?: number }

/** The restore runs on the server (a large library takes a while): asked about until it's over. Done,
 *  the sessions are gone too, so a refused question (401) means done: to the sign-in page. */
async function follow(started: RestoreStatus) {
  let st = started
  while (st.state === 'running') {
    await new Promise((r) => setTimeout(r, 1500))
    const res = await fetch('/api/v1/admin/restore', { credentials: 'same-origin' }).catch(() => null)
    if (res?.status === 401) {
      st = { state: 'done' }
      break
    }
    if (res?.ok) st = await res.json()
  }
  if (st.state === 'failed') throw new ApiError(500, st.error ?? 'restore_failed')
  alert((st.created ? t('backup.restored', { date: dateTime(st.created) }) : t('backup.restoredShort')) + (st.covers_missing ? `\n${t('backup.restoredCovers')}` : ''))
  window.location.href = '/'
}

async function restoreKept(b: Backup) {
  if (!confirm(t('backup.restoreConfirm', { date: dateTime(b.created) }))) return
  busy.value = 'restore'
  try {
    await follow(await api<RestoreStatus>(`/admin/backups/${encodeURIComponent(b.name)}/restore`, { method: 'POST' }))
  } catch (e) {
    ui.notify(errorMessage(e), true)
  } finally {
    busy.value = ''
  }
}

async function restoreFile(f: File | undefined) {
  if (file.value) file.value.value = ''
  if (!f || !confirm(t('backup.restoreFileConfirm', { name: f.name }))) return
  busy.value = 'restore'
  try {
    // the file as the request body (no form): large ones go as they are read
    const res = await fetch('/api/v1/admin/restore', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/octet-stream' }, body: f })
    const data = await res.json().catch(() => null)
    if (!res.ok) throw new ApiError(res.status, typeof data?.detail === 'string' ? data.detail : res.status === 413 ? 'backup_too_large' : 'unknown')
    await follow(data)
  } catch (e) {
    ui.notify(errorMessage(e), true)
    await load().catch(() => {})
  } finally {
    busy.value = ''
  }
}
</script>

<template>
  <section class="flex flex-col gap-5 rounded-2xl border border-line p-5 md:p-6">
    <div>
      <h2 class="text-xl font-bold">{{ t('backup.title') }}</h2>
      <p class="mt-1 text-sm font-light leading-relaxed text-muted">{{ t('backup.desc') }}</p>
      <p class="mt-2 text-[13px] leading-relaxed text-danger">{{ t('backup.secret') }}</p>
    </div>
    <div class="flex flex-wrap gap-2.5">
      <button type="button" class="h-11 rounded-full bg-ink px-5 text-sm text-on-ink disabled:opacity-50" :disabled="!!busy" @click="backupNow">
        {{ busy === 'backup' ? t('backup.making') : t('backup.make') }}
      </button>
      <label class="flex h-11 cursor-pointer items-center gap-2 rounded-full border border-line-strong px-4 text-sm hover:border-ink" :class="busy ? 'pointer-events-none opacity-50' : ''">
        <Upload :size="16" :stroke-width="1.7" />{{ busy === 'restore' ? t('backup.restoring') : t('backup.fromFile') }}
        <input ref="file" type="file" accept=".gz,.tgz,application/gzip" class="sr-only" :disabled="!!busy" @change="restoreFile(($event.target as HTMLInputElement).files?.[0])" />
      </label>
    </div>

    <div class="flex flex-col">
      <h3 class="mb-1 text-[15px] font-medium">{{ t('backup.kept', { n: keep }) }}</h3>
      <p v-if="!items.length" class="text-sm font-light text-muted">{{ t('backup.none') }}</p>
      <div v-for="b in items" :key="b.name" class="flex items-center gap-2 border-b border-line py-2.5 last:border-0">
        <span class="flex min-w-0 flex-1 flex-col">
          <span class="text-[15px]">{{ dateTime(b.created) }}</span>
          <span class="truncate text-[12px] text-muted">{{ b.name }} · {{ size(b.size) }}</span>
        </span>
        <a :href="`/api/v1/admin/backups/${encodeURIComponent(b.name)}`" :download="b.name" class="grid size-10 flex-none place-items-center rounded-full text-muted hover:bg-surface hover:text-ink" :aria-label="t('backup.download')" :title="t('backup.download')">
          <Download :size="18" :stroke-width="1.7" />
        </a>
        <button type="button" class="grid size-10 flex-none place-items-center rounded-full text-muted hover:bg-surface hover:text-ink disabled:opacity-40" :disabled="!!busy" :aria-label="t('backup.restore')" :title="t('backup.restore')" @click="restoreKept(b)">
          <RotateCcw :size="18" :stroke-width="1.7" />
        </button>
        <button type="button" class="grid size-10 flex-none place-items-center rounded-full text-muted hover:bg-surface hover:text-danger disabled:opacity-40" :disabled="!!busy" :aria-label="t('backup.delete')" :title="t('backup.delete')" @click="remove(b)">
          <Trash2 :size="18" :stroke-width="1.7" />
        </button>
      </div>
    </div>
    <p class="text-[12px] font-light leading-relaxed text-muted">{{ t('backup.restoreHelp') }}</p>
  </section>
</template>
