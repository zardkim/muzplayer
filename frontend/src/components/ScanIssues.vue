<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { TriangleAlert } from '@lucide/vue'
import { api, query } from '../api'
import ChoiceChip from './ChoiceChip.vue'
import LoadMore from './LoadMore.vue'
import SearchField from './SearchField.vue'

// Admin → library: every file the last scans could not read (backend scan_issues), kept until the
// next scan of its place. By kind (damaged, cut short, format, permission, gone), with what to do;
// a song the library still has from before opens its album (it is marked "read error" in lists).
const { t } = useI18n()

interface Issue { path: string; message: string; at: string; track_id: number | null; album_id: number | null }
const KINDS = ['damaged', 'cut', 'format', 'permission', 'gone', 'other'] as const
type Kind = (typeof KINDS)[number]
function kindOf(message: string): Kind {
  return /sync to MPEG frame|header not found|unknown duration/i.test(message) ? 'damaged'
    : /file said|read 0 bytes|truncated|unexpected end/i.test(message) ? 'cut'
      : /unsupported file/i.test(message) ? 'format'
        : /permission denied|errno 13/i.test(message) ? 'permission'
          : /no such file|broken link/i.test(message) ? 'gone' : 'other'
}

const items = ref<(Issue & { kind: Kind })[]>([])
const total = ref(0)
const loading = ref(false)
const q = ref('')
const kind = ref<Kind | null>(null)
let asked = 0

async function load(more = false) {
  const mine = ++asked
  loading.value = true
  try {
    const r = await api<{ items: Issue[]; total: number }>(`/admin/scan/issues${query({ q: q.value.trim() || undefined, offset: more ? items.value.length : 0, limit: 500 })}`)
    if (mine !== asked) return
    const rows = r.items.map((x) => ({ ...x, kind: kindOf(x.message) }))
    items.value = more ? [...items.value, ...rows] : rows
    total.value = r.total
  } finally {
    if (mine === asked) loading.value = false
  }
}
onMounted(() => load())
let timer: number | undefined
watch(q, () => {
  clearTimeout(timer)
  timer = window.setTimeout(() => load(), 300)
})

const counts = computed(() => Object.fromEntries(KINDS.map((k) => [k, items.value.filter((x) => x.kind === k).length])) as Record<Kind, number>)
const shown = computed(() => (kind.value ? items.value.filter((x) => x.kind === kind.value) : items.value))
const split = (path: string) => {
  const at = path.lastIndexOf('/')
  return at < 0 ? { dir: '', name: path } : { dir: path.slice(0, at), name: path.slice(at + 1) }
}
</script>

<template>
  <section v-if="total || q" class="flex flex-col gap-3 rounded-2xl border border-danger/30 p-4 md:p-5">
    <div class="flex items-center gap-2">
      <TriangleAlert :size="18" :stroke-width="1.8" class="flex-none text-danger" aria-hidden="true" />
      <h3 class="text-[17px] font-bold">{{ t('admin.issuesTitle', { n: total }) }}</h3>
    </div>
    <p class="-mt-1 text-[13px] text-muted">{{ t('admin.issuesHelp') }}</p>
    <div class="flex flex-wrap items-center gap-2">
      <SearchField v-model="q" :placeholder="t('admin.issuesSearch')" class="w-full sm:w-64" />
      <div class="-mr-4 flex gap-1.5 overflow-x-auto pr-4 [scrollbar-width:none] md:mr-0 md:flex-wrap md:pr-0">
        <ChoiceChip :active="kind === null" small @click="kind = null">{{ t('search.tab_all') }} <span class="opacity-60">{{ items.length }}</span></ChoiceChip>
        <template v-for="k in KINDS" :key="k">
          <ChoiceChip v-if="counts[k]" :active="kind === k" small @click="kind = k">{{ t(`admin.issueKind_${k}`) }} <span class="opacity-60">{{ counts[k] }}</span></ChoiceChip>
        </template>
      </div>
    </div>
    <!-- one kind at a time says what to do once, above its files -->
    <p v-if="kind" class="rounded-xl bg-surface px-3 py-2.5 text-[13px] leading-relaxed">{{ t(`admin.fileError_${kind}`) }}</p>
    <ul class="flex max-h-[60vh] flex-col overflow-y-auto" :class="loading ? 'opacity-60' : ''">
      <li v-for="x in shown" :key="x.path" class="flex flex-col gap-0.5 border-b border-line py-2.5 last:border-0">
        <span class="flex items-start justify-between gap-3">
          <span class="min-w-0 break-all text-[14px] font-medium">{{ split(x.path).name }}</span>
          <RouterLink v-if="x.album_id" :to="{ name: 'album', params: { id: x.album_id } }" class="flex-none text-[13px] text-accent hover:underline">{{ t('admin.issueOpenAlbum') }}</RouterLink>
        </span>
        <span v-if="split(x.path).dir" class="break-all text-[12px] text-muted">{{ split(x.path).dir }}</span>
        <span class="text-[12px] text-subtle">
          <span class="mr-1 rounded bg-danger/10 px-1 text-danger">{{ t(`admin.issueKind_${x.kind}`) }}</span>{{ x.message }}
        </span>
      </li>
      <li v-if="!shown.length && !loading" class="py-3 text-[14px] text-muted">{{ t('search.noResults') }}</li>
    </ul>
    <LoadMore v-if="items.length < total" small :loading="loading" @click="load(true)" />
  </section>
</template>
