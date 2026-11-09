<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { Plus, RotateCcw, X } from '@lucide/vue'
import { api } from '../api'
import { errorMessage } from '../i18n'
import { useUi } from '../stores/ui'
import type { AliasEntry, ArtistDetail } from '../types'
import BaseModal from './BaseModal.vue'

// An admin's list of an artist's other names (머라이어 캐리 for Mariah Carey): the ones looked up
// (artist_aliases.py) can be taken out (hidden: a later lookup leaves them out), names can be added.
const props = defineProps<{ artist: ArtistDetail }>()
const emit = defineEmits<{ close: []; changed: [aliases: string[], entries: AliasEntry[]] }>()
const { t } = useI18n()
const ui = useUi()
const entries = ref<AliasEntry[]>((props.artist.alias_entries ?? []).map((a) => ({ ...a })))
const adding = ref('')
const busy = ref(false)

function add() {
  const name = adding.value.trim()
  if (!name) return
  const same = entries.value.find((a) => a.name.toLowerCase() === name.toLowerCase())
  if (same) same.hidden = false
  else entries.value.push({ name, source: 'manual', hidden: false })
  adding.value = ''
}
async function save() {
  busy.value = true
  try {
    const r = await api<{ aliases: string[]; alias_entries: AliasEntry[] }>(`/artists/${props.artist.id}/aliases`, {
      method: 'PUT',
      body: { names: entries.value.filter((a) => !a.hidden).map((a) => a.name) },
    })
    emit('changed', r.aliases, r.alias_entries)
    emit('close')
  } catch (e) {
    ui.notify(errorMessage(e), true)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <BaseModal :title="t('aliases.title')" @close="emit('close')">
    <div class="flex flex-col gap-4">
      <p class="text-[14px] leading-relaxed text-muted">{{ t('aliases.help', { name: artist.name }) }}</p>
      <ul class="flex flex-wrap gap-2">
        <li v-for="a in entries" :key="a.name" class="flex h-9 items-center gap-1 rounded-full border pl-3.5 pr-1 text-[14px]" :class="a.hidden ? 'border-dashed border-line-strong text-subtle line-through' : 'border-line-strong'">
          {{ a.name }}<span class="ml-1 text-[11px] text-muted no-underline">{{ t(`aliases.source_${a.source}`) }}</span>
          <button v-if="a.hidden" type="button" class="grid size-7 place-items-center rounded-full text-muted hover:text-ink" :aria-label="t('aliases.restore')" :title="t('aliases.restore')" @click="a.hidden = false"><RotateCcw :size="14" /></button>
          <button
            v-else
            type="button"
            class="grid size-7 place-items-center rounded-full text-muted hover:text-ink"
            :aria-label="t('aliases.remove')"
            :title="t('aliases.remove')"
            @click="a.source === 'manual' ? entries.splice(entries.indexOf(a), 1) : (a.hidden = true)"
          ><X :size="14" /></button>
        </li>
        <li v-if="!entries.length" class="text-[14px] text-muted">{{ t('aliases.none') }}</li>
      </ul>
      <form class="flex gap-2" @submit.prevent="add">
        <input v-model="adding" maxlength="200" :placeholder="t('aliases.addPlaceholder')" class="h-11 min-w-0 flex-1 rounded-full bg-surface px-4 text-base outline-none focus:ring-2 focus:ring-ink" />
        <button type="submit" class="grid size-11 flex-none place-items-center rounded-full bg-surface hover:bg-surface-2" :aria-label="t('aliases.add')"><Plus :size="18" /></button>
      </form>
      <button type="button" class="h-11 self-end rounded-full bg-ink px-6 text-[15px] text-on-ink disabled:opacity-50" :disabled="busy" @click="save">{{ t('common.save') }}</button>
    </div>
  </BaseModal>
</template>
