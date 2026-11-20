<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { RefreshCw } from '@lucide/vue'
import { api } from '../api'
import { errorMessage } from '../i18n'
import { useUi } from '../stores/ui'
import type { ScanJob } from '../types'

// Admins: an album's or a chart's metadata read again — its folders rescanned (every file's tags,
// size and date again; the songs keep their ids, stars and plays), not the whole library.
const props = defineProps<{ folders: string[]; large?: boolean }>()
const emit = defineEmits<{ done: [] }>()
const { t } = useI18n()
const ui = useUi()
const busy = ref(false)

async function finished(id: number): Promise<ScanJob> {
  for (;;) {
    await new Promise((r) => setTimeout(r, 800))
    const job = await api<ScanJob>(`/admin/scan/${id}`)
    if (job.status !== 'running') return job
  }
}

async function refresh() {
  if (busy.value || !props.folders.length) return
  busy.value = true
  try {
    for (const folder of props.folders) {
      const job = await finished((await api<ScanJob>('/admin/scan', { method: 'POST', body: { folder, mode: 'rescan' } })).id)
      if (job.status !== 'done') {
        return ui.notify(job.error_summary?.startsWith('folder_not_found') ? t('errors.folder_not_found') : t('admin.scanFailed'), true)
      }
    }
    ui.notify(t('metadata.done'))
    emit('done')
  } catch (e) {
    ui.notify(errorMessage(e), true)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <button
    type="button"
    class="flex flex-none items-center gap-1.5 rounded-full border border-line-strong px-3.5 text-[14px] hover:border-ink disabled:opacity-60"
    :class="large ? 'h-11' : 'h-[38px]'"
    :disabled="busy"
    :title="t('metadata.help')"
    @click="refresh"
  >
    <RefreshCw :size="16" :stroke-width="1.6" :class="busy ? 'animate-spin' : ''" />{{ busy ? t('metadata.running') : t('metadata.refresh') }}
  </button>
</template>
