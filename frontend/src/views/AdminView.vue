<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { Plus, RefreshCw } from '@lucide/vue'
import { api } from '../api'
import { dateTime } from '../format'
import { errorMessage } from '../i18n'
import { useAuth } from '../stores/auth'
import { useUi } from '../stores/ui'
import type { ScanJob, User } from '../types'
import BaseModal from '../components/BaseModal.vue'
import PageHeader from '../components/PageHeader.vue'

const { t } = useI18n()
const auth = useAuth()
const ui = useUi()

const job = ref<ScanJob | null>(null)
const hasMissing = ref(false)
const autoScan = ref(0)
const users = ref<User[]>([])
let poll: number | undefined

async function loadScan() {
  const r = await api<{ job: ScanJob | null; has_missing: boolean; auto_scan_minutes: number }>('/admin/scan/latest')
  job.value = r.job
  hasMissing.value = r.has_missing
  autoScan.value = r.auto_scan_minutes
  clearTimeout(poll)
  if (r.job?.status === 'running') poll = window.setTimeout(loadScan, 1500)
}

async function loadUsers() {
  users.value = (await api<{ items: User[] }>('/admin/users')).items
}

onMounted(() => {
  loadScan().catch((e) => ui.notify(errorMessage(e), true))
  loadUsers().catch((e) => ui.notify(errorMessage(e), true))
})
onUnmounted(() => clearTimeout(poll))

async function startScan() {
  try {
    job.value = await api<ScanJob>('/admin/scan', { method: 'POST' })
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
          <button
            type="button"
            class="flex h-11 items-center gap-2 rounded-full bg-ink px-5 text-sm text-white disabled:opacity-50"
            :disabled="job?.status === 'running'"
            @click="startScan"
          >
            <RefreshCw :size="18" :class="job?.status === 'running' ? 'animate-spin' : ''" />{{ t('admin.startScan') }}
          </button>
        </div>
      </div>

      <div v-if="job?.status === 'running'" class="flex flex-col gap-2">
        <div class="text-[13px] text-muted">{{ t('admin.scanning', { n: job.scanned }) }}</div>
        <div class="h-1.5 overflow-hidden rounded-full bg-line"><div class="h-1.5 w-2/5 animate-pulse rounded-full bg-accent" /></div>
      </div>
      <p v-else-if="job" class="text-[13px]" :class="job.status === 'failed' ? 'text-danger' : 'text-muted'">
        <template v-if="job.status === 'failed'">{{ t('admin.scanFailed') }} · </template>{{ t('admin.lastScan', { time: dateTime(job.finished_at ?? job.started_at) }) }}
      </p>
      <p v-else class="text-[13px] text-muted">{{ t('admin.neverScanned') }}</p>

      <div v-if="job" class="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div class="flex flex-col gap-1 rounded-xl bg-surface px-4 py-3.5"><span class="text-[13px] text-muted">{{ t('admin.added') }}</span><span class="font-display text-[22px] font-bold">{{ job.added }}</span></div>
        <div class="flex flex-col gap-1 rounded-xl bg-surface px-4 py-3.5"><span class="text-[13px] text-muted">{{ t('admin.updated') }}</span><span class="font-display text-[22px] font-bold">{{ job.updated }}</span></div>
        <div class="flex flex-col gap-1 rounded-xl bg-surface px-4 py-3.5"><span class="text-[13px] text-muted">{{ t('admin.missing') }}</span><span class="font-display text-[22px] font-bold text-accent">{{ job.missing }}</span></div>
        <div class="flex flex-col gap-1 rounded-xl bg-surface px-4 py-3.5"><span class="text-[13px] text-muted">{{ t('admin.errors') }}</span><span class="font-display text-[22px] font-bold text-danger">{{ job.errors }}</span></div>
      </div>
      <details v-if="job?.error_summary" class="text-[13px] text-muted">
        <summary class="cursor-pointer">{{ t('admin.errorDetails') }}</summary>
        <pre class="mt-2 max-h-60 overflow-auto whitespace-pre-wrap rounded-xl bg-surface p-3 text-xs">{{ job.error_summary }}</pre>
      </details>
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
        <button type="submit" class="mt-1 h-12 rounded-full bg-ink text-white">{{ t('common.create') }}</button>
      </form>
    </BaseModal>

    <BaseModal v-if="resetFor" :title="t('admin.resetPassword')" @close="resetFor = null">
      <form class="flex flex-col gap-3.5" @submit.prevent="submitReset">
        <label class="flex flex-col gap-1.5 text-[13px] text-muted">
          {{ t('admin.resetPasswordFor', { name: resetFor.display_name }) }}
          <input v-model="resetPassword" type="password" autocomplete="new-password" required minlength="8" :class="field" />
        </label>
        <button type="submit" class="h-12 rounded-full bg-ink text-white">{{ t('common.save') }}</button>
      </form>
    </BaseModal>
  </div>
</template>
