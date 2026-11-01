<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ChevronDown, Film, Folder } from '@lucide/vue'
import { api } from '../api'
import { errorMessage } from '../i18n'
import { useUi } from '../stores/ui'
import { VIDEO_KINDS, type Video, type VideoFile, type VideoKind } from '../types'
import BaseModal from './BaseModal.vue'

// Registering the video files the NAS keeps in library/video: each gets a kind (and a title,
// the file name to begin with). Files already registered are marked. All files in one list, or
// by folder (a folder can be added at once); the view picked last is remembered.
const { t } = useI18n()
const ui = useUi()
const emit = defineEmits<{ close: [] }>()
const files = ref<VideoFile[] | null>(null)
const folder = ref(true)
const error = ref('')
const kind = ref<VideoKind>('mv')
const titles = ref<Record<string, string>>({})
const busy = ref(false)
const view = computed({
  get: () => (ui.views.videoFiles === 'folders' ? 'folders' : 'all'),
  set: (v: 'all' | 'folders') => (ui.views = { ...ui.views, videoFiles: v }),
})
const open = ref<Set<string>>(new Set())

const dirOf = (path: string) => (path.includes('/') ? path.slice(0, path.lastIndexOf('/')) : '')
const nameOf = (path: string) => path.slice(path.lastIndexOf('/') + 1)
const folders = computed(() => {
  const map = new Map<string, VideoFile[]>()
  for (const f of files.value ?? []) {
    const d = dirOf(f.path)
    map.set(d, [...(map.get(d) ?? []), f])
  }
  return [...map.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([dir, items]) => ({ dir, items }))
})

onMounted(async () => {
  try {
    const r = await api<{ folder: boolean; items: VideoFile[] }>('/videos/files')
    folder.value = r.folder
    files.value = r.items
    titles.value = Object.fromEntries(r.items.map((f) => [f.path, nameOf(f.path).replace(/\.[^.]+$/, '')]))
    // folders still holding unregistered files start open
    open.value = new Set(folders.value.filter((g) => g.items.some((f) => !f.video_id)).map((g) => g.dir))
  } catch (e) {
    error.value = errorMessage(e)
  }
})

async function register(f: VideoFile): Promise<boolean> {
  try {
    const v = await api<Video>('/videos/files', { method: 'POST', body: { path: f.path, kind: kind.value, title: titles.value[f.path] } })
    f.video_id = v.id
    return true
  } catch (e) {
    ui.notify(errorMessage(e), true)
    return false
  }
}

async function add(f: VideoFile) {
  if (await register(f)) ui.notify(t('videos.added'))
}

async function addFolder(items: VideoFile[]) {
  busy.value = true
  let n = 0
  for (const f of items) if (!f.video_id && titles.value[f.path]?.trim() && (await register(f))) n++
  busy.value = false
  if (n) ui.notify(t('videos.added'))
}

function toggle(dir: string) {
  const s = new Set(open.value)
  if (s.has(dir)) s.delete(dir)
  else s.add(dir)
  open.value = s
}

const size = (n: number) => (n >= 1e9 ? `${(n / 1e9).toFixed(1)} GB` : `${Math.max(1, Math.round(n / 1e6))} MB`)
</script>

<template>
  <BaseModal wide :title="t('videos.filesTitle')" @close="emit('close')">
    <div class="flex flex-col gap-4">
      <p class="text-[14px] leading-relaxed text-muted">{{ t('videos.filesHint') }}</p>
      <div class="flex flex-wrap items-center gap-1.5" role="radiogroup" :aria-label="t('videos.kind')">
        <button
          v-for="k in VIDEO_KINDS"
          :key="k"
          type="button"
          role="radio"
          :aria-checked="kind === k"
          class="h-9 rounded-full px-3.5 text-[14px]"
          :class="kind === k ? 'bg-ink text-on-ink' : 'bg-surface'"
          @click="kind = k"
        >{{ t(`videos.kinds.${k}`) }}</button>
        <!-- all files, or by folder -->
        <div class="ml-auto flex items-center rounded-full bg-surface p-1" role="radiogroup" :aria-label="t('common.viewMode')">
          <button
            v-for="v in (['all', 'folders'] as const)"
            :key="v"
            type="button"
            role="radio"
            :aria-checked="view === v"
            class="h-8 rounded-full px-3 text-[13px]"
            :class="view === v ? 'bg-bg text-ink shadow-sm' : 'text-muted hover:text-ink'"
            @click="view = v"
          >{{ v === 'all' ? t('videos.viewAll') : t('videos.viewFolders') }}</button>
        </div>
      </div>

      <p v-if="error" class="text-[14px] text-danger" role="alert">{{ error }}</p>
      <p v-else-if="!files" class="text-[14px] text-muted" role="status">{{ t('common.loading') }}</p>
      <p v-else-if="!folder" class="text-[14px] leading-relaxed text-muted">{{ t('videos.noFolder') }}</p>
      <p v-else-if="!files.length" class="text-[14px] text-muted">{{ t('videos.noFiles') }}</p>
      <template v-else>
        <template v-for="g in view === 'folders' ? folders : [{ dir: null, items: files }]" :key="g.dir ?? 'all'">
          <div v-if="g.dir !== null" class="flex items-center gap-2 border-b border-line pb-2 pt-1">
            <button type="button" class="flex min-w-0 flex-1 items-center gap-2.5 text-left" :aria-expanded="open.has(g.dir)" @click="toggle(g.dir)">
              <Folder :size="18" :stroke-width="1.5" class="flex-none text-muted" />
              <span class="flex min-w-0 flex-col">
                <span class="truncate text-[15px] font-medium">{{ g.dir || t('videos.rootFolder') }}</span>
                <span class="text-[12px] text-muted">{{ t('videos.folderCount', { n: g.items.length, done: g.items.filter((f) => f.video_id).length }) }}</span>
              </span>
              <ChevronDown :size="18" :stroke-width="1.5" class="ml-1 flex-none text-muted transition-transform" :class="open.has(g.dir) ? 'rotate-180' : ''" />
            </button>
            <button
              type="button"
              class="h-8 flex-none rounded-full border border-line-strong px-3 text-[13px] disabled:opacity-40"
              :disabled="busy || g.items.every((f) => f.video_id)"
              @click="addFolder(g.items)"
            >{{ t('videos.addFolder') }}</button>
          </div>
          <ul v-if="g.dir === null || open.has(g.dir)" class="flex flex-col gap-2">
            <li v-for="f in g.items" :key="f.path" class="flex items-center gap-3 rounded-xl bg-surface p-2.5">
              <span class="grid size-10 flex-none place-items-center rounded-lg bg-bg text-muted"><Film :size="18" :stroke-width="1.4" /></span>
              <span class="flex min-w-0 flex-1 flex-col gap-1">
                <input
                  v-model="titles[f.path]"
                  :aria-label="t('videos.fileTitle')"
                  :disabled="!!f.video_id"
                  maxlength="500"
                  class="h-9 min-w-0 rounded-lg bg-bg px-2.5 text-[14px] outline-none focus:ring-2 focus:ring-ink disabled:opacity-60"
                />
                <span class="truncate text-[12px] text-muted">{{ g.dir === null ? f.path : nameOf(f.path) }} · {{ size(f.size) }}</span>
              </span>
              <button
                type="button"
                class="h-9 flex-none rounded-full px-3.5 text-[14px] disabled:opacity-50"
                :class="f.video_id ? 'text-muted' : 'bg-ink text-on-ink'"
                :disabled="busy || !!f.video_id || !titles[f.path]?.trim()"
                @click="add(f)"
              >{{ f.video_id ? t('videos.registered') : t('videos.register') }}</button>
            </li>
          </ul>
        </template>
      </template>
    </div>
  </BaseModal>
</template>
