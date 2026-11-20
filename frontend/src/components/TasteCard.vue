<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { X } from '@lucide/vue'
import { api } from '../api'
import { errorMessage } from '../i18n'
import { useUi } from '../stores/ui'
import type { TasteOut } from '../types'
import SmartWizard from './SmartWizard.vue'

// Settings → my taste: what the smart playlist wizard was told (users.taste), changed with the
// wizard again, and the songs left out of the lists made from it (each one can come back).
const { t } = useI18n()
const ui = useUi()
const data = ref<TasteOut | null>(null)
const editing = ref(false)

async function load() {
  try {
    data.value = await api<TasteOut>('/taste')
  } catch (e) {
    ui.notify(errorMessage(e), true)
  }
}
onMounted(load)

const names = computed(() => new Map(data.value?.artists.map((a) => [a.id, a.name]) ?? []))
// one line per answer given ("" when none)
const lines = computed(() => {
  const x = data.value?.taste
  if (!x) return []
  const artists = (ids: number[]) => ids.map((i) => names.value.get(i)).filter(Boolean).join(', ')
  return [
    [t('smartWizard.q.genres'), x.genres.join(', ')],
    [t('smartWizard.q.artists'), artists(x.artists)],
    [t('smartWizard.q.decades'), x.decades.map((d) => t('smartWizard.decade', { n: d })).join(', ')],
    [t('smartWizard.excludeGenres'), x.exclude_genres.join(', ')],
    [t('smartWizard.excludeArtists'), artists(x.exclude_artists)],
  ].filter(([, v]) => v)
})

async function bringBack(id: number) {
  try {
    await api(`/taste/exclude/${id}`, { method: 'DELETE' })
    await load()
  } catch (e) {
    ui.notify(errorMessage(e), true)
  }
}
</script>

<template>
  <div class="flex flex-col gap-4">
    <p class="text-[13px] font-light text-muted">{{ t('settings.tasteHelp') }}</p>
    <template v-if="data">
      <dl v-if="lines.length" class="flex flex-col gap-2.5 text-[14px]">
        <div v-for="[q, v] in lines" :key="q" class="flex flex-col">
          <dt class="text-[13px] text-muted">{{ q }}</dt>
          <dd>{{ v }}</dd>
        </div>
      </dl>
      <p v-else class="text-[14px] text-muted">{{ data.taste ? t('settings.tasteAny') : t('settings.tasteNone') }}</p>
      <button type="button" class="pill self-start" @click="editing = true">{{ data.taste ? t('settings.tasteEdit') : t('settings.tasteStart') }}</button>

      <template v-if="data.tracks.length">
        <h3 class="mt-2 font-medium">{{ t('settings.tasteExcluded', { n: data.tracks.length }) }}</h3>
        <ul class="flex flex-col divide-y divide-line">
          <li v-for="tr in data.tracks" :key="tr.id" class="flex items-center gap-2 py-2 text-[14px]">
            <span class="min-w-0 flex-1 truncate">{{ tr.title }}<span v-if="tr.artist" class="text-muted"> · {{ tr.artist }}</span></span>
            <button type="button" class="grid size-9 flex-none place-items-center text-muted" :aria-label="t('settings.tasteBringBack', { title: tr.title })" :title="t('settings.tasteBringBack', { title: tr.title })" @click="bringBack(tr.id)">
              <X :size="16" />
            </button>
          </li>
        </ul>
      </template>
    </template>
    <SmartWizard v-if="editing" taste-only @close="editing = false" @saved="(editing = false), load()" />
  </div>
</template>
