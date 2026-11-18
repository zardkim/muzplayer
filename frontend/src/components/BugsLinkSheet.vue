<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { Check, ExternalLink } from '@lucide/vue'
import { api, query } from '../api'
import { errorMessage } from '../i18n'
import { useUi } from '../stores/ui'
import type { ArtistDetail, BugsCandidate } from '../types'
import BaseModal from './BaseModal.vue'
import SearchField from './SearchField.vue'

// An admin's link of an artist to Bugs (bugs_artists.py): one of Bugs' artists for a name (its own,
// or another typed), "not on Bugs", or unlinked (looked up again after the next scan).
const props = defineProps<{ artist: ArtistDetail }>()
const emit = defineEmits<{ close: []; changed: [artist: ArtistDetail] }>()
const { t } = useI18n()
const ui = useUi()
const q = ref(props.artist.tag_name ?? props.artist.name)
const items = ref<BugsCandidate[] | null>(props.artist.bugs?.candidates ?? null)
const busy = ref(false)
const error = ref('')

async function search() {
  busy.value = true
  error.value = ''
  try {
    items.value = (await api<{ items: BugsCandidate[] }>(`/artists/${props.artist.id}/bugs${query({ q: q.value.trim() })}`)).items
  } catch (e) {
    error.value = errorMessage(e)
  } finally {
    busy.value = false
  }
}
onMounted(() => {
  if (!items.value?.length) void search()
})
async function save(body: { bugs_id?: number | null; none?: boolean }) {
  busy.value = true
  try {
    emit('changed', await api<ArtistDetail>(`/artists/${props.artist.id}/bugs`, { method: 'PUT', body }))
    emit('close')
  } catch (e) {
    ui.notify(errorMessage(e), true)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <BaseModal :title="t('bugs.linkTitle')" @close="emit('close')">
    <div class="flex flex-col gap-4">
      <p class="text-[14px] leading-relaxed text-muted">{{ t('bugs.linkHelp') }}</p>
      <form class="flex gap-2" @submit.prevent="search">
        <SearchField v-model="q" :placeholder="t('bugs.searchPlaceholder')" class="min-w-0 flex-1" />
        <button type="submit" class="h-11 flex-none rounded-full bg-surface px-4 text-[14px] hover:bg-surface-2" :disabled="busy">{{ t('videos.searchButton') }}</button>
      </form>
      <p v-if="error" role="alert" class="text-[13px] text-danger">{{ error }}</p>
      <ul v-if="items" class="flex flex-col">
        <li v-for="c in items" :key="c.bugs_id" class="flex items-center gap-2 border-b border-line py-1.5 last:border-0">
          <button type="button" class="flex min-w-0 flex-1 items-center gap-2 rounded-xl px-2 py-2 text-left hover:bg-surface disabled:opacity-50" :disabled="busy" @click="save({ bugs_id: c.bugs_id })">
            <span class="flex min-w-0 flex-col">
              <span class="truncate text-[15px]">{{ c.name }}</span>
              <span class="text-[12px] text-muted">{{ c.type }}</span>
            </span>
            <Check v-if="artist.bugs?.id === c.bugs_id" :size="16" class="ml-auto flex-none text-accent" />
          </button>
          <a :href="`https://music.bugs.co.kr/artist/${c.bugs_id}`" target="_blank" rel="noopener" class="grid size-9 flex-none place-items-center rounded-full text-muted hover:text-ink" :aria-label="t('bugs.open')" :title="t('bugs.open')"><ExternalLink :size="15" /></a>
        </li>
        <li v-if="!items.length" class="py-2 text-[14px] text-muted">{{ t('search.noResults') }}</li>
      </ul>
      <div class="flex flex-wrap justify-end gap-2">
        <button v-if="artist.bugs?.id" type="button" class="pill" :disabled="busy" @click="save({ bugs_id: null })">{{ t('bugs.unlink') }}</button>
        <button type="button" class="pill" :disabled="busy" @click="save({ bugs_id: null, none: true })">{{ t('bugs.notOnBugs') }}</button>
      </div>
    </div>
  </BaseModal>
</template>
