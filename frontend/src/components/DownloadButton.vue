<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { CircleCheck, Download } from '@lucide/vue'
import { errorMessage } from '../i18n'
import { canSave, offline, removeList, saveList, savedList, type SavedList } from '../offline'
import { useUi } from '../stores/ui'

// Saves an album or playlist on this device for offline listening (offline.ts); tapping a saved
// one offers to remove it. Hidden where saving can't work (no https).
const props = defineProps<{ list: Omit<SavedList, 'at'> }>()
const { t } = useI18n()
const ui = useUi()

const saved = computed(() => savedList(props.list.key))
const progress = computed(() => offline.progress[props.list.key])
// saved, but the list has songs the saved copy lacks (added since, or saving stopped)
const partial = computed(() => !!saved.value && props.list.tracks.some((t) => !t.missing && !(String(t.id) in offline.files)))

async function tap() {
  if (progress.value) return
  if (saved.value && !partial.value) {
    if (confirm(t('offline.removeConfirm', { name: props.list.title }))) await removeList(props.list.key)
    return
  }
  try {
    await saveList(props.list)
    ui.notify(t('offline.saved', { name: props.list.title }))
  } catch (e) {
    ui.notify(t('offline.failed', { error: errorMessage(e) }), true)
  }
}
</script>

<template>
  <button
    v-if="canSave()"
    type="button"
    class="flex items-center gap-1.5 rounded-full border border-line-strong px-4 text-[15px]"
    :class="saved && !partial && !progress ? 'text-accent' : ''"
    :aria-label="saved && !partial ? t('offline.remove') : t('offline.save')"
    @click="tap"
  >
    <template v-if="progress">
      <span class="size-4 animate-spin rounded-full border-2 border-line-strong border-t-ink" />
      <span class="font-display">{{ progress.done }}/{{ progress.total }}</span>
    </template>
    <template v-else>
      <CircleCheck v-if="saved && !partial" :size="17" :stroke-width="1.5" />
      <Download v-else :size="17" :stroke-width="1.5" />
      {{ saved && !partial ? t('offline.savedShort') : partial ? t('offline.update') : t('offline.saveShort') }}
    </template>
  </button>
</template>
