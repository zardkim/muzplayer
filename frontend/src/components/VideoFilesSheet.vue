<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { Film } from '@lucide/vue'
import { api } from '../api'
import { errorMessage } from '../i18n'
import { useUi } from '../stores/ui'
import { VIDEO_KINDS, type Video, type VideoFile, type VideoKind } from '../types'
import BaseModal from './BaseModal.vue'

// Registering the video files the NAS keeps in library/video: each gets a kind (and a title,
// the file name to begin with). Files already registered are marked.
const { t } = useI18n()
const ui = useUi()
const emit = defineEmits<{ close: [] }>()
const files = ref<VideoFile[] | null>(null)
const folder = ref(true)
const error = ref('')
const kind = ref<VideoKind>('mv')
const titles = ref<Record<string, string>>({})

onMounted(async () => {
  try {
    const r = await api<{ folder: boolean; items: VideoFile[] }>('/videos/files')
    folder.value = r.folder
    files.value = r.items
    titles.value = Object.fromEntries(r.items.map((f) => [f.path, f.path.split('/').pop()!.replace(/\.[^.]+$/, '')]))
  } catch (e) {
    error.value = errorMessage(e)
  }
})

async function add(f: VideoFile) {
  try {
    const v = await api<Video>('/videos/files', { method: 'POST', body: { path: f.path, kind: kind.value, title: titles.value[f.path] } })
    f.video_id = v.id
    ui.notify(t('videos.added'))
  } catch (e) {
    ui.notify(errorMessage(e), true)
  }
}

const size = (n: number) => (n >= 1e9 ? `${(n / 1e9).toFixed(1)} GB` : `${Math.max(1, Math.round(n / 1e6))} MB`)
</script>

<template>
  <BaseModal :title="t('videos.filesTitle')" @close="emit('close')">
    <div class="flex flex-col gap-4">
      <p class="text-[14px] leading-relaxed text-muted">{{ t('videos.filesHint') }}</p>
      <div class="flex flex-wrap gap-1.5" role="radiogroup" :aria-label="t('videos.kind')">
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
      </div>
      <p v-if="error" class="text-[14px] text-danger" role="alert">{{ error }}</p>
      <p v-else-if="!files" class="text-[14px] text-muted" role="status">{{ t('common.loading') }}</p>
      <p v-else-if="!folder" class="text-[14px] leading-relaxed text-muted">{{ t('videos.noFolder') }}</p>
      <p v-else-if="!files.length" class="text-[14px] text-muted">{{ t('videos.noFiles') }}</p>
      <ul v-else class="flex flex-col gap-2">
        <li v-for="f in files" :key="f.path" class="flex items-center gap-3 rounded-xl bg-surface p-2.5">
          <span class="grid size-10 flex-none place-items-center rounded-lg bg-bg text-muted"><Film :size="18" :stroke-width="1.4" /></span>
          <span class="flex min-w-0 flex-1 flex-col gap-1">
            <input
              v-model="titles[f.path]"
              :aria-label="t('videos.fileTitle')"
              :disabled="!!f.video_id"
              maxlength="500"
              class="h-9 min-w-0 rounded-lg bg-bg px-2.5 text-[14px] outline-none focus:ring-2 focus:ring-ink disabled:opacity-60"
            />
            <span class="truncate text-[12px] text-muted">{{ f.path }} · {{ size(f.size) }}</span>
          </span>
          <button
            type="button"
            class="h-9 flex-none rounded-full px-3.5 text-[14px] disabled:opacity-50"
            :class="f.video_id ? 'text-muted' : 'bg-ink text-on-ink'"
            :disabled="!!f.video_id || !titles[f.path]?.trim()"
            @click="add(f)"
          >{{ f.video_id ? t('videos.registered') : t('videos.register') }}</button>
        </li>
      </ul>
    </div>
  </BaseModal>
</template>
