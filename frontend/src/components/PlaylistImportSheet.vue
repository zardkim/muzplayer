<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { CircleAlert, CircleCheck, CircleHelp, Globe } from '@lucide/vue'
import { ApiError } from '../api'
import { errorMessage } from '../i18n'
import { useLibrary } from '../stores/library'
import { useUi } from '../stores/ui'
import BaseModal from './BaseModal.vue'

// A playlist file from another player (.m3u, .m3u8, .pls) read against the library (backend
// playlist_import.py): each entry with the song it became here (its path in this library), or
// marked missing. Made into a new playlist of the songs found, in the file's order.
type How = 'path' | 'file' | 'tags' | 'missing' | 'ambiguous' | 'web'
interface Item {
  path: string
  label: string
  how: How
  track: { id: number; title: string; artist: string; path: string } | null
}
interface Report {
  name: string
  total: number
  found: number
  items: Item[]
  playlist_id?: number
  added?: number
  skipped?: number
  kept_missing?: number
}

const props = defineProps<{ file: File }>()
const emit = defineEmits<{ close: [] }>()
const { t } = useI18n()
const router = useRouter()
const library = useLibrary()
const ui = useUi()

const report = ref<Report | null>(null)
const error = ref('')
const name = ref(props.file.name.replace(/\.(m3u8?|pls|txt)$/i, ''))
const show = ref<'all' | 'found' | 'missing'>('all')
// where the songs go: a new playlist, or the end of one I may change
const target = ref<number | 'new'>('new')
const busy = ref(false)

async function send(create: boolean): Promise<Report> {
  const q = new URLSearchParams({ name: name.value.trim() })
  if (create) q.set('create', 'true')
  if (create && target.value !== 'new') q.set('target_id', String(target.value))
  // the file as it is: the server reads its encoding (CP949 from Korean Windows players, else UTF-8)
  const res = await fetch(`/api/v1/playlists/import?${q}`, { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/octet-stream' }, body: props.file })
  const data = await res.json().catch(() => null)
  if (!res.ok) throw new ApiError(res.status, typeof data?.detail === 'string' ? data.detail : res.status === 413 ? 'playlist_file_too_large' : 'unknown')
  return data
}
onMounted(async () => {
  try {
    report.value = await send(false)
  } catch (e) {
    error.value = errorMessage(e)
  }
})

const missing = computed(() => (report.value ? report.value.total - report.value.found : 0))
const shown = computed(() =>
  (report.value?.items ?? []).filter((x) => show.value === 'all' || (show.value === 'found') === !!x.track),
)
const ICONS = { path: CircleCheck, file: CircleCheck, tags: CircleCheck, missing: CircleAlert, ambiguous: CircleHelp, web: Globe }

const ready = computed(() => (target.value === 'new' ? !!report.value?.found && !!name.value.trim() : !!report.value))
async function create() {
  if (!ready.value) return
  busy.value = true
  try {
    const r = await send(true)
    await library.loadPlaylists().catch(() => {})
    ui.notify(
      t(target.value === 'new' ? 'importList.made' : 'importList.added', { n: r.added ?? 0 }) +
        (r.skipped ? ` ${t('importList.skipped', { n: r.skipped })}` : '') +
        (r.kept_missing ? ` ${t('importList.kept', { n: r.kept_missing })}` : ''),
    )
    emit('close')
    router.push({ name: 'playlist', params: { id: r.playlist_id } })
  } catch (e) {
    ui.notify(errorMessage(e), true)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <BaseModal wide :title="t('importList.title')" @close="emit('close')">
    <div class="flex flex-col gap-4">
      <p v-if="error" class="text-danger">{{ error }}</p>
      <p v-else-if="!report" class="font-light text-muted">{{ t('importList.reading', { name: file.name }) }}</p>
      <template v-else>
        <div class="flex flex-col gap-1.5 text-[13px] text-muted">
          <label for="import-target">{{ t('importList.to') }}</label>
          <select id="import-target" v-model="target" class="h-12 rounded-full bg-surface px-4 text-base text-ink outline-none focus:ring-2 focus:ring-ink">
            <option value="new">{{ t('importList.toNew') }}</option>
            <option v-for="p in library.editablePlaylists" :key="p.id" :value="p.id">{{ p.name }}</option>
          </select>
        </div>
        <label v-if="target === 'new'" class="flex flex-col gap-1.5 text-[13px] text-muted">
          {{ t('playlists.name') }}
          <input v-model="name" maxlength="200" class="h-12 rounded-full bg-surface px-4 text-base text-ink outline-none focus:ring-2 focus:ring-ink" />
        </label>
        <p class="text-[15px]">
          {{ t('importList.summary', { total: report.total, found: report.found }) }}
          <span v-if="missing" class="text-danger">{{ t('importList.missingN', { n: missing }) }}</span>
        </p>
        <p class="-mt-2 text-[13px] font-light text-muted">{{ t('importList.help') }}</p>

        <div class="flex gap-2">
          <button
            v-for="k in (['all', 'found', 'missing'] as const)"
            :key="k"
            type="button"
            class="h-8 rounded-full border border-line-strong px-3 text-[13px] hover:border-ink"
            :aria-pressed="show === k"
            :class="show === k ? 'border-ink bg-ink text-on-ink' : ''"
            @click="show = k"
          >{{ t(`importList.show_${k}`) }}</button>
        </div>

        <ul class="flex max-h-[45vh] flex-col overflow-y-auto rounded-2xl border border-line">
          <li v-for="(x, i) in shown" :key="i" class="flex items-start gap-3 border-b border-line px-3 py-2.5 last:border-0">
            <component :is="ICONS[x.how]" :size="18" :stroke-width="1.6" class="mt-0.5 flex-none" :class="x.track ? 'text-ink' : 'text-danger'" />
            <span class="flex min-w-0 flex-1 flex-col gap-0.5">
              <template v-if="x.track">
                <span class="truncate text-[14px]">{{ x.track.artist ? `${x.track.artist} - ` : '' }}{{ x.track.title }}</span>
                <span class="truncate text-[12px] text-muted" :title="x.path">{{ x.track.path }}</span>
              </template>
              <template v-else>
                <span class="truncate text-[14px]">{{ x.label }}</span>
                <span class="truncate text-[12px] text-muted" :title="x.path">{{ x.path }}</span>
              </template>
            </span>
            <span class="flex-none rounded px-1.5 text-[11px] leading-[18px]" :class="x.track ? 'bg-surface text-muted' : 'bg-danger/10 text-danger'">{{ t(`importList.how_${x.how}`) }}</span>
          </li>
        </ul>

        <div class="flex justify-end gap-2">
          <button type="button" class="h-11 rounded-full border border-line-strong px-5 text-[15px] hover:border-ink" @click="emit('close')">{{ t('common.cancel') }}</button>
          <button type="button" class="h-11 rounded-full bg-ink px-5 text-[15px] text-on-ink disabled:opacity-40" :disabled="busy || !ready" @click="create">{{ t(target === 'new' ? 'importList.create' : 'importList.addTo', { n: report.found }) }}</button>
        </div>
      </template>
    </div>
  </BaseModal>
</template>
