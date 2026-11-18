<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ChevronDown, ChevronUp, Plus, Trash2 } from '@lucide/vue'
import { api } from '../api'
import { errorMessage } from '../i18n'
import { useUi } from '../stores/ui'
import { kindName, loadVideoKinds, videoKinds, type VideoKindItem } from '../videoKinds'
import BaseModal from './BaseModal.vue'

// An admin's kinds of music videos (video_kinds): added, renamed, ordered (the page's sections
// follow it), removed (their videos go to "other", which stays). Each change is saved at once.
const emit = defineEmits<{ close: []; changed: [] }>()
const { t } = useI18n()
const ui = useUi()
const adding = ref('')
const busy = ref(false)
loadVideoKinds(true)

async function run(work: () => Promise<unknown>) {
  if (busy.value) return
  busy.value = true
  try {
    await work()
    await loadVideoKinds(true)
    emit('changed')
  } catch (e) {
    ui.notify(errorMessage(e), true)
  } finally {
    busy.value = false
  }
}
// a built-in kind left empty goes back to its own name; an added one keeps the name it had
function rename(k: VideoKindItem, e: Event) {
  const input = e.target as HTMLInputElement
  const name = input.value.trim()
  const builtIn = !/^k\d+$/.test(k.key)
  if (name === (k.name ?? '') || (!name && !builtIn)) {
    input.value = k.name ?? ''
    return
  }
  run(() => api(`/video-kinds/${k.key}`, { method: 'PATCH', body: name ? { name } : { default_name: true } }))
}
const move = (k: VideoKindItem, by: -1 | 1) => run(() => api(`/video-kinds/${k.key}`, { method: 'PATCH', body: { move: by } }))
function remove(k: VideoKindItem) {
  const ask = k.count ? t('videoKinds.removeConfirmVideos', { name: kindName(k.key), n: k.count, other: kindName('other') }) : t('videoKinds.removeConfirm', { name: kindName(k.key) })
  if (confirm(ask)) run(() => api(`/video-kinds/${k.key}`, { method: 'DELETE' }))
}
function add() {
  const name = adding.value.trim()
  if (!name) return
  run(async () => {
    await api('/video-kinds', { method: 'POST', body: { name } })
    adding.value = ''
  })
}
</script>

<template>
  <BaseModal :title="t('videoKinds.title')" @close="emit('close')">
    <div class="flex flex-col gap-4">
      <p class="text-[14px] leading-relaxed text-muted">{{ t('videoKinds.help') }}</p>
      <ul class="flex flex-col gap-2">
        <li v-for="(k, i) in videoKinds.list" :key="k.key" class="flex items-center gap-1.5">
          <input
            :value="k.name ?? ''"
            :placeholder="kindName(k.key)"
            maxlength="50"
            enterkeyhint="done"
            :aria-label="t('videoKinds.name')"
            class="field h-11 min-w-0 flex-1 px-4"
            :disabled="busy"
            @change="rename(k, $event)"
            @keydown.enter="($event.target as HTMLInputElement).blur()"
          />
          <span class="w-10 flex-none text-right text-[13px] tabular-nums text-muted" :title="t('videoKinds.count', { n: k.count })">{{ k.count }}</span>
          <button type="button" class="grid size-9 flex-none place-items-center rounded-full text-muted hover:bg-surface hover:text-ink disabled:opacity-30" :disabled="busy || i === 0" :aria-label="t('videoKinds.up')" :title="t('videoKinds.up')" @click="move(k, -1)"><ChevronUp :size="18" /></button>
          <button type="button" class="grid size-9 flex-none place-items-center rounded-full text-muted hover:bg-surface hover:text-ink disabled:opacity-30" :disabled="busy || i === videoKinds.list.length - 1" :aria-label="t('videoKinds.down')" :title="t('videoKinds.down')" @click="move(k, 1)"><ChevronDown :size="18" /></button>
          <button
            type="button"
            class="grid size-9 flex-none place-items-center rounded-full text-muted hover:bg-surface hover:text-danger disabled:opacity-30"
            :disabled="busy || k.fixed"
            :aria-label="t('videoKinds.remove')"
            :title="k.fixed ? t('videoKinds.fixed') : t('videoKinds.remove')"
            @click="remove(k)"
          ><Trash2 :size="17" /></button>
        </li>
      </ul>
      <form class="flex gap-2" @submit.prevent="add">
        <input v-model="adding" maxlength="50" :placeholder="t('videoKinds.addPlaceholder')" class="field h-11 min-w-0 flex-1 px-4" :disabled="busy" />
        <button type="submit" class="grid size-11 flex-none place-items-center rounded-full bg-ink text-on-ink disabled:opacity-40" :disabled="busy || !adding.trim()" :aria-label="t('videoKinds.add')" :title="t('videoKinds.add')"><Plus :size="18" /></button>
      </form>
    </div>
  </BaseModal>
</template>
