<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Search } from '@lucide/vue'
import { api, query } from '../api'
import { dateTime } from '../format'
import { errorMessage } from '../i18n'
import type { ActivityEntry, User } from '../types'
import PageHeader from '../components/PageHeader.vue'

// Admin → log (backend activity.py): sign-ins, failed ones, and every change made on the admin
// page, newest first; by kind, by person, or searched (name, detail, address).
const { t } = useI18n()
const KINDS = ['login', 'failed', 'admin'] as const
const kind = ref<(typeof KINDS)[number] | null>(null)
const userId = ref<number | null>(null)
const q = ref('')
const items = ref<ActivityEntry[]>([])
const total = ref(0)
const users = ref<User[]>([])
const loading = ref(false)
const error = ref('')
let asked = 0

async function load(more = false) {
  const mine = ++asked
  loading.value = true
  error.value = ''
  try {
    const r = await api<{ items: ActivityEntry[]; total: number }>(
      `/admin/logs${query({ kind: kind.value ?? undefined, user_id: userId.value ?? undefined, q: q.value.trim() || undefined, offset: more ? items.value.length : 0, limit: 100 })}`,
    )
    if (mine !== asked) return
    items.value = more ? [...items.value, ...r.items] : r.items
    total.value = r.total
  } catch (e) {
    error.value = errorMessage(e)
  } finally {
    if (mine === asked) loading.value = false
  }
}
onMounted(() => {
  load()
  api<{ items: User[] }>('/admin/users').then((r) => (users.value = r.items), () => {})
})
watch([kind, userId], () => load())
let timer: number | undefined
watch(q, () => {
  clearTimeout(timer)
  timer = window.setTimeout(() => load(), 300)
})

// an admin change: "PATCH /admin/users/{user_id} | family | is_admin=True" → its name, what, fields
const ROUTES: Record<string, string> = {
  'POST /admin/scan': 'scan',
  'POST /admin/scan/cancel': 'scanCancel',
  'POST /admin/covers/rebuild': 'covers',
  'DELETE /admin/missing-tracks': 'purge',
  'PUT /admin/folders': 'folders',
  'POST /admin/users': 'userAdd',
  'PATCH /admin/users/{user_id}': 'userEdit',
  'DELETE /admin/users/{user_id}': 'userDelete',
  'PUT /admin/signup': 'signup',
  'PUT /admin/integrations': 'keys',
  'POST /admin/artist-images/lookup': 'photos',
  'PUT /admin/artists/{artist_id}/image': 'photoSet',
  'DELETE /admin/artists/{artist_id}/image': 'photoRemove',
  'POST /admin/merge/{kind}': 'merge',
  'DELETE /admin/merge/{kind}': 'unmerge',
  'POST /admin/albums/{album_id}/notes/report': 'notes',
  'PUT /admin/albums/{album_id}/notes': 'notes',
  'POST /admin/search-index': 'searchIndex',
  'POST /admin/books/abs-import': 'absImport',
  'POST /admin/banners/generate': 'bannerMake',
  'POST /admin/banners': 'bannerAdd',
  'DELETE /admin/banners/{banner_id}': 'bannerDelete',
}
function describe(e: ActivityEntry): { what: string; detail: string } {
  if (e.action !== 'admin') {
    const reason = e.detail ? t(`logs.reason.${e.detail}`) : ''
    return { what: t(`logs.action.${e.action}`), detail: reason }
  }
  const [route, ...rest] = e.detail.split(' | ')
  const key = ROUTES[route]
  return { what: key ? t(`logs.route.${key}`) : route, detail: rest.join(' · ') }
}
const rows = computed(() => items.value.map((e) => ({ ...e, ...describe(e) })))
const tone = (action: string) =>
  action === 'login_failed' || action === 'login_locked' ? 'bg-[#fdecec] text-danger' : action === 'admin' ? 'bg-accent-soft text-accent-strong' : 'bg-surface text-muted'
</script>

<template>
  <div class="flex flex-col gap-6">
    <PageHeader :title="t('logs.title')" :sub="t('logs.sub', { n: total })" />

    <div class="flex flex-wrap items-center gap-2">
      <div class="-mr-5 flex min-w-0 gap-2 overflow-x-auto pr-5 [scrollbar-width:none] md:mr-0 md:pr-0">
        <button
          v-for="k in [null, ...KINDS]"
          :key="k ?? 'all'"
          type="button"
          class="h-[38px] flex-none rounded-full border px-4 text-[15px]"
          :class="kind === k ? 'border-ink bg-ink text-on-ink' : 'border-line-strong bg-bg'"
          :aria-pressed="kind === k"
          @click="kind = k"
        >
          {{ k ? t(`logs.kind.${k}`) : t('logs.kind.all') }}
        </button>
      </div>
      <select v-model="userId" class="h-[38px] rounded-full border border-line-strong bg-bg px-3 text-[14px]" :aria-label="t('logs.user')">
        <option :value="null">{{ t('logs.allUsers') }}</option>
        <option v-for="u in users" :key="u.id" :value="u.id">{{ u.display_name }} ({{ u.username }})</option>
      </select>
      <label class="flex h-[38px] min-w-0 flex-1 items-center gap-2 rounded-full bg-surface px-4 sm:max-w-72">
        <Search :size="16" :stroke-width="1.5" class="flex-none text-muted" aria-hidden="true" />
        <span class="sr-only">{{ t('logs.search') }}</span>
        <input v-model="q" type="search" maxlength="100" :placeholder="t('logs.search')" class="min-w-0 flex-1 bg-transparent text-[14px] outline-none" />
      </label>
    </div>

    <p v-if="error" class="text-danger" role="alert">{{ error }}</p>
    <p v-else-if="!loading && !items.length" class="font-light text-muted">{{ t('logs.empty') }}</p>

    <ul class="flex flex-col" :class="loading ? 'opacity-60' : ''">
      <li v-for="e in rows" :key="e.id" class="flex flex-col gap-1 border-b border-surface py-3 md:flex-row md:items-center md:gap-4">
        <span class="flex justify-between gap-3 md:contents">
          <span class="w-40 flex-none font-display text-[13px] text-muted">{{ dateTime(e.at) }}</span>
          <span v-if="e.ip" class="font-display text-[12px] text-subtle md:hidden">{{ e.ip }}</span>
        </span>
        <span class="flex min-w-0 flex-1 flex-wrap items-center gap-x-2 gap-y-1">
          <span class="rounded-full px-2.5 py-0.5 text-[12px]" :class="tone(e.action)">{{ e.what }}</span>
          <span class="text-[14px] font-medium">{{ e.username || '–' }}</span>
          <span v-if="e.detail" class="min-w-0 break-all text-[13px] text-muted">{{ e.detail }}</span>
        </span>
        <span v-if="e.ip" class="hidden flex-none font-display text-[12px] text-subtle md:inline">{{ e.ip }}</span>
      </li>
    </ul>

    <button v-if="items.length < total" type="button" class="h-11 self-center rounded-full border border-line-strong px-6 text-[15px] disabled:opacity-40" :disabled="loading" @click="load(true)">
      {{ t('common.loadMore') }}
    </button>
  </div>
</template>
