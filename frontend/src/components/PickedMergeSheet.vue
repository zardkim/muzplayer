<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ExternalLink, Link2 } from '@lucide/vue'
import { api } from '../api'
import { errorMessage } from '../i18n'
import { useUi } from '../stores/ui'
import type { ArtistDetail } from '../types'
import BaseModal from './BaseModal.vue'
import BugsLinkSheet from './BugsLinkSheet.vue'

// Admin: the artists or genres picked on their list page, made one (backend merge.py). The name to
// keep is chosen here; artists show their Bugs artist, which can be checked or set before merging
// (the kept one's link carries on). Suggested first: the one linked to Bugs, then the most songs.
const props = defineProps<{ kind: 'artist' | 'genre'; picked: { id: number; name: string; songs: number }[] }>()
const emit = defineEmits<{ close: []; merged: [] }>()
const { t } = useI18n()
const ui = useUi()
const details = ref<Record<number, ArtistDetail>>({})
const keep = ref(props.picked[0].id)
const busy = ref(false)
const linking = ref<ArtistDetail | null>(null)

const rows = computed(() =>
  [...props.picked].sort((a, b) => Number(!details.value[a.id]?.bugs?.id) - Number(!details.value[b.id]?.bugs?.id) || b.songs - a.songs),
)
onMounted(async () => {
  if (props.kind !== 'artist') {
    keep.value = rows.value[0].id
    return
  }
  const all = await Promise.all(props.picked.map((p) => api<ArtistDetail>(`/artists/${p.id}`).catch(() => null)))
  details.value = Object.fromEntries(all.filter((a): a is ArtistDetail => !!a).map((a) => [a.id, a]))
  keep.value = rows.value[0].id
})

function bugsText(id: number) {
  const b = details.value[id]?.bugs
  if (!details.value[id]) return ''
  if (b?.id) return [t('merge.bugsName', { name: b.name || t('merge.bugsNoName') }), b.type].filter(Boolean).join(' · ')
  return t(`merge.bugs_${b?.source === 'none' || b?.source === 'unsure' ? b.source : 'pending'}`)
}

async function run() {
  busy.value = true
  try {
    const r = await api<{ merged: number }>(`/admin/merge/${props.kind}`, {
      method: 'POST',
      body: { keep: keep.value, ids: props.picked.map((p) => p.id).filter((i) => i !== keep.value) },
    })
    ui.notify(t('merge.done', { n: r.merged }))
    emit('merged')
  } catch (e) {
    ui.notify(errorMessage(e), true)
  } finally {
    busy.value = false
  }
}
const keptName = computed(() => props.picked.find((p) => p.id === keep.value)?.name ?? '')
</script>

<template>
  <BaseModal :title="t('merge.pickedTitle', { n: picked.length })" @close="emit('close')">
    <div class="flex flex-col gap-4">
      <p class="text-[13px] font-light leading-relaxed text-muted">{{ t(kind === 'artist' ? 'merge.pickedHelpArtist' : 'merge.pickedHelp') }}</p>
      <div class="flex flex-col">
        <label v-for="p in rows" :key="p.id" class="flex items-center gap-3 border-b border-line py-2.5 last:border-0">
          <input v-model="keep" type="radio" :value="p.id" name="merge-keep" class="size-4 flex-none accent-accent" />
          <span class="flex min-w-0 flex-1 flex-col">
            <span class="truncate text-[15px]">{{ p.name }}<span class="text-[13px] text-muted"> · {{ t('common.tracks', p.songs) }}</span></span>
            <span v-if="kind === 'artist'" class="truncate text-[12px]" :class="details[p.id]?.bugs?.id ? 'text-accent' : 'text-muted'">{{ bugsText(p.id) || '…' }}</span>
          </span>
          <span v-if="keep === p.id" class="flex-none text-[12px] text-accent">{{ t('merge.kept') }}</span>
          <template v-if="kind === 'artist' && details[p.id]">
            <a v-if="details[p.id].bugs?.url" :href="details[p.id].bugs!.url!" target="_blank" rel="noopener" class="grid size-9 flex-none place-items-center rounded-full text-muted hover:text-ink" :aria-label="t('bugs.open')" :title="t('bugs.open')"><ExternalLink :size="15" /></a>
            <button type="button" class="grid size-9 flex-none place-items-center rounded-full text-muted hover:bg-surface hover:text-ink" :aria-label="`${t('bugs.linkTitle')}: ${p.name}`" :title="t('bugs.linkTitle')" @click.prevent="linking = details[p.id]">
              <Link2 :size="15" :stroke-width="1.6" />
            </button>
          </template>
        </label>
      </div>
      <button type="button" class="h-11 rounded-full bg-ink px-5 text-[15px] text-on-ink disabled:opacity-50" :disabled="busy || picked.length < 2" @click="run">
        {{ t('merge.mergeInto', { name: keptName }) }}
      </button>
      <p class="text-[12px] font-light text-muted">{{ t('merge.undoHelpPicked') }}</p>
    </div>
    <BugsLinkSheet v-if="linking" :artist="linking" @close="linking = null" @changed="(a) => (details = { ...details, [a.id]: a })" />
  </BaseModal>
</template>
