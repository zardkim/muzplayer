<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api'
import { errorMessage } from '../i18n'
import { useUi } from '../stores/ui'
import type { VideoListItem } from '../types'
import BaseModal from './BaseModal.vue'

// Taking a music video's sound out as a song (backend extract.py): m4a (AAC kept as it is) or mp3.
// The job runs in the background; the jobs sheet shows it.
const props = defineProps<{ video: VideoListItem }>()
const emit = defineEmits<{ close: []; queued: [] }>()
const { t } = useI18n()
const ui = useUi()
interface Status { folder_ok: boolean; ytdlp: string | null; youtube: boolean; format: 'm4a' | 'mp3' }
const status = ref<Status | null>(null)
const format = ref<'m4a' | 'mp3'>('m4a')
const busy = ref(false)
onMounted(async () => {
  status.value = await api<Status>('/extract/status').catch(() => null)
  if (status.value) format.value = status.value.format
})
const blocked = () => {
  const s = status.value
  if (!s) return ''
  if (!s.folder_ok) return t('extract.noFolder')
  if (props.video.youtube_id && !s.youtube) return t('extract.youtubeOff')
  if (props.video.youtube_id && !s.ytdlp) return t('extract.noYtdlp')
  return ''
}
async function start() {
  busy.value = true
  try {
    await api(`/videos/${props.video.id}/extract`, { method: 'POST', body: { format: format.value } })
    ui.notify(t('extract.queued'))
    emit('queued')
  } catch (e) {
    ui.notify(errorMessage(e), true)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <BaseModal :title="t('extract.title')" @close="emit('close')">
    <div class="flex flex-col gap-4">
      <p class="text-[15px] font-medium">{{ video.title }}</p>
      <p class="text-[13px] leading-relaxed text-muted">{{ t('extract.help') }}</p>
      <div class="flex flex-col gap-2" role="radiogroup" :aria-label="t('extract.format')">
        <label v-for="f in (['m4a', 'mp3'] as const)" :key="f" class="flex items-start gap-3 rounded-xl border px-3.5 py-3" :class="format === f ? 'border-ink' : 'border-line'">
          <input v-model="format" type="radio" :value="f" class="mt-1 accent-accent" />
          <span class="flex flex-col"><span class="text-[15px] font-medium uppercase">{{ f }}</span><span class="text-[13px] text-muted">{{ t(`extract.format_${f}`) }}</span></span>
        </label>
      </div>
      <p v-if="blocked()" class="text-[13px] leading-relaxed text-danger">{{ blocked() }}</p>
      <button type="button" class="h-12 rounded-full bg-ink text-on-ink disabled:opacity-50" :disabled="busy || !status || !!blocked()" @click="start">{{ t('extract.start') }}</button>
    </div>
  </BaseModal>
</template>
