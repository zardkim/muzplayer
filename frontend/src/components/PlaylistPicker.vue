<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ListMusic, Plus } from '@lucide/vue'
import { errorMessage } from '../i18n'
import { useLibrary } from '../stores/library'
import { useUi } from '../stores/ui'
import BaseModal from './BaseModal.vue'

const { t } = useI18n()
const library = useLibrary()
const ui = useUi()
const newName = ref('')
const busy = ref(false)

onMounted(() => library.loadPlaylists().catch(() => {}))

async function add(playlistId: number) {
  if (!ui.playlistPicker || busy.value) return
  busy.value = true
  try {
    await library.addToPlaylist(playlistId, ui.playlistPicker)
    ui.notify(t('common.added'))
    ui.playlistPicker = null
  } catch (e) {
    ui.notify(errorMessage(e), true)
  } finally {
    busy.value = false
  }
}

async function createAndAdd() {
  const name = newName.value.trim()
  if (!name) return
  try {
    const p = await library.createPlaylist(name)
    await add(p.id)
  } catch (e) {
    ui.notify(errorMessage(e), true)
  }
}
</script>

<template>
  <BaseModal :title="t('playlists.chooseTitle')" @close="ui.playlistPicker = null">
    <form class="mb-3 flex gap-2" @submit.prevent="createAndAdd">
      <label class="sr-only" for="new-playlist">{{ t('playlists.name') }}</label>
      <input
        id="new-playlist"
        v-model="newName"
        maxlength="200"
        :placeholder="t('playlists.new')"
        class="h-11 min-w-0 flex-1 rounded-full bg-surface px-4 text-base outline-none focus:ring-2 focus:ring-ink"
      />
      <button type="submit" class="grid size-11 place-items-center rounded-full bg-ink text-white disabled:opacity-40" :disabled="!newName.trim()" :aria-label="t('common.create')">
        <Plus :size="20" />
      </button>
    </form>
    <ul class="flex flex-col">
      <li v-for="p in library.playlists.filter((x) => x.kind !== 'smart')" :key="p.id">
        <button type="button" class="flex w-full items-center gap-3 rounded-xl px-2 py-2 text-left hover:bg-surface" :disabled="busy" @click="add(p.id)">
          <span class="grid size-11 place-items-center rounded-lg bg-surface text-ink"><ListMusic :size="20" :stroke-width="1.3" /></span>
          <span class="flex flex-col">
            <span>{{ p.name }}</span>
            <span class="text-[13px] font-light text-muted">{{ t('common.tracks', p.track_count ?? 0) }}</span>
          </span>
        </button>
      </li>
    </ul>
  </BaseModal>
</template>
