<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Pencil, Play, Shuffle, Trash2 } from '@lucide/vue'
import { api } from '../api'
import { errorMessage } from '../i18n'
import { useLibrary } from '../stores/library'
import { usePlayer } from '../stores/player'
import { useUi } from '../stores/ui'
import type { PlaylistDetail } from '../types'
import BaseModal from '../components/BaseModal.vue'
import TrackList from '../components/TrackList.vue'

const props = defineProps<{ id: string }>()
const { t } = useI18n()
const router = useRouter()
const player = usePlayer()
const library = useLibrary()
const ui = useUi()
const playlist = ref<PlaylistDetail | null>(null)
const error = ref('')
const renaming = ref(false)
const newName = ref('')

async function load() {
  try {
    playlist.value = await api<PlaylistDetail>(`/playlists/${props.id}`)
  } catch (e) {
    error.value = errorMessage(e)
  }
}
onMounted(load)
const tracks = computed(() => playlist.value?.entries.map((e) => e.track) ?? [])

async function run(fn: () => Promise<unknown>) {
  try {
    await fn()
  } catch (e) {
    ui.notify(errorMessage(e), true)
  }
  await load()
  library.loadPlaylists().catch(() => {})
}

function remove(i: number) {
  const entry = playlist.value!.entries[i]
  run(() => api(`/playlists/${props.id}/tracks/${entry.entry_id}`, { method: 'DELETE' }))
}

function move(i: number, dir: -1 | 1) {
  const ids = playlist.value!.entries.map((e) => e.entry_id)
  ;[ids[i], ids[i + dir]] = [ids[i + dir], ids[i]]
  run(() => api(`/playlists/${props.id}/order`, { method: 'PUT', body: { entry_ids: ids } }))
}

function rename() {
  const name = newName.value.trim()
  if (!name) return
  renaming.value = false
  run(() => api(`/playlists/${props.id}`, { method: 'PATCH', body: { name } }))
}

async function destroy() {
  if (!playlist.value || !confirm(t('playlists.deleteConfirm', { name: playlist.value.name }))) return
  try {
    await api(`/playlists/${props.id}`, { method: 'DELETE' })
    await library.loadPlaylists()
    router.replace({ name: 'playlists' })
  } catch (e) {
    ui.notify(errorMessage(e), true)
  }
}
</script>

<template>
  <p v-if="error" class="text-muted">{{ error }}</p>
  <div v-else-if="playlist" class="flex flex-col gap-7">
    <div class="flex flex-col gap-3">
      <h1 class="text-4xl font-bold tracking-tight">{{ playlist.name }}</h1>
      <p class="text-sm text-muted">{{ t('common.tracks', playlist.entries.length) }}</p>
      <div class="flex flex-wrap gap-2">
        <button type="button" class="flex h-11 items-center gap-2 rounded-full bg-accent px-5 font-semibold text-bg disabled:opacity-40" :disabled="!tracks.length" @click="player.playTracks(tracks, 0, { shuffle: false })">
          <Play :size="18" fill="currentColor" />{{ t('common.playAll') }}
        </button>
        <button type="button" class="flex h-11 items-center gap-2 rounded-full border border-line-strong px-5 font-semibold disabled:opacity-40" :disabled="!tracks.length" @click="player.playTracks(tracks, 0, { shuffle: true })">
          <Shuffle :size="18" />{{ t('common.shuffleAll') }}
        </button>
        <button type="button" class="grid size-11 place-items-center rounded-full bg-surface-2" :aria-label="t('common.rename')" @click="(newName = playlist.name), (renaming = true)">
          <Pencil :size="18" />
        </button>
        <button type="button" class="grid size-11 place-items-center rounded-full bg-surface-2 text-danger" :aria-label="t('common.delete')" @click="destroy">
          <Trash2 :size="18" />
        </button>
      </div>
    </div>
    <p v-if="!tracks.length" class="text-muted">{{ t('playlists.emptyTracks') }}</p>
    <TrackList :tracks="tracks" editable @remove="remove" @move="move" />

    <BaseModal v-if="renaming" :title="t('common.rename')" @close="renaming = false">
      <form class="flex flex-col gap-4" @submit.prevent="rename">
        <label class="flex flex-col gap-1.5 text-[13px] text-muted">
          {{ t('playlists.name') }}
          <input v-model="newName" maxlength="200" class="h-11 rounded-xl border border-line bg-bg px-3.5 text-base text-ink outline-none focus:border-accent" />
        </label>
        <button type="submit" class="h-11 rounded-full bg-accent font-semibold text-bg">{{ t('common.save') }}</button>
      </form>
    </BaseModal>
  </div>
</template>
