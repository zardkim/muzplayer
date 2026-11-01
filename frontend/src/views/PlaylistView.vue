<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Pencil, SlidersHorizontal, Trash2 } from '@lucide/vue'
import { api } from '../api'
import { errorMessage } from '../i18n'
import { useLibrary } from '../stores/library'
import { useUi } from '../stores/ui'
import type { Playlist, PlaylistDetail } from '../types'
import BaseModal from '../components/BaseModal.vue'
import DownloadButton from '../components/DownloadButton.vue'
import PageHeader from '../components/PageHeader.vue'
import PlayActions from '../components/PlayActions.vue'
import SmartRulesSheet from '../components/SmartRulesSheet.vue'
import TrackList from '../components/TrackList.vue'

const props = defineProps<{ id: string }>()
const { t } = useI18n()
const router = useRouter()
const library = useLibrary()
const ui = useUi()
const playlist = ref<PlaylistDetail | null>(null)
const error = ref('')
const renaming = ref(false)
const newName = ref('')
const editingRules = ref(false)
const smart = computed(() => playlist.value?.kind === 'smart')

async function load() {
  try {
    playlist.value = await api<PlaylistDetail>(`/playlists/${props.id}`)
  } catch (e) {
    error.value = errorMessage(e)
  }
}
onMounted(load)
const tracks = computed(() => playlist.value?.entries.map((e) => e.track) ?? [])
// what the download button saves (offline.ts); the cover is the first song's album
const saveAs = computed(() => {
  const first = tracks.value.find((x) => x.album_id)
  return {
    key: `playlist:${props.id}`, title: playlist.value?.name ?? '', subtitle: '', link: `/playlists/${props.id}`,
    cover: first ? { albumId: first.album_id!, hasCover: first.has_cover, v: first.cover_v } : null, tracks: tracks.value,
  }
})

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

function rulesSaved(_p: Playlist) {
  editingRules.value = false
  load()
  library.loadPlaylists().catch(() => {})
}

// a smart playlist's songs as they are now, kept as an ordinary playlist
async function snapshot() {
  try {
    const p = await library.createPlaylist(`${playlist.value!.name} ${new Date().toLocaleDateString()}`)
    await library.addToPlaylist(p.id, tracks.value)
    ui.notify(t('common.saved'))
  } catch (e) {
    ui.notify(errorMessage(e), true)
  }
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
  <p v-if="error" class="font-light text-muted">{{ error }}</p>
  <div v-else-if="playlist" class="flex flex-col gap-5">
    <PageHeader :title="playlist.name" :sub="smart ? `${t('smart.badge')} · ${t('common.tracks', playlist.entries.length)}` : t('common.tracks', playlist.entries.length)" />
    <div class="flex flex-wrap gap-2">
      <PlayActions :tracks="tracks" :add="false" />
      <button v-if="smart" type="button" class="flex h-[38px] items-center gap-1.5 rounded-full border border-line-strong px-4 text-[15px]" @click="editingRules = true">
        <SlidersHorizontal :size="15" :stroke-width="1.5" />{{ t('smart.edit') }}
      </button>
      <DownloadButton v-if="tracks.length" class="h-[38px]" :list="saveAs" />
      <button v-if="smart" type="button" class="h-[38px] rounded-full border border-line-strong px-4 text-[15px] disabled:opacity-40" :disabled="!tracks.length" @click="snapshot">{{ t('common.saveAsPlaylist') }}</button>
      <button v-else type="button" class="grid size-[38px] place-items-center rounded-full border border-line-strong" :aria-label="t('common.rename')" @click="(newName = playlist.name), (renaming = true)">
        <Pencil :size="16" :stroke-width="1.4" />
      </button>
      <button type="button" class="grid size-[38px] place-items-center rounded-full border border-line-strong text-danger" :aria-label="t('common.delete')" @click="destroy">
        <Trash2 :size="16" :stroke-width="1.4" />
      </button>
    </div>
    <p v-if="!tracks.length" class="font-light text-muted">{{ smart ? t('common.empty') : t('playlists.emptyTracks') }}</p>
    <TrackList :tracks="tracks" :editable="!smart" @remove="remove" @move="move" />
    <SmartRulesSheet v-if="editingRules" :playlist="playlist" @close="editingRules = false" @saved="rulesSaved" />

    <BaseModal v-if="renaming" :title="t('common.rename')" @close="renaming = false">
      <form class="flex flex-col gap-4" @submit.prevent="rename">
        <label class="flex flex-col gap-1.5 text-[13px] text-muted">
          {{ t('playlists.name') }}
          <input v-model="newName" maxlength="200" class="h-12 rounded-full bg-surface px-4 text-base text-ink outline-none focus:ring-2 focus:ring-ink" />
        </label>
        <button type="submit" class="h-12 rounded-full bg-ink text-on-ink">{{ t('common.save') }}</button>
      </form>
    </BaseModal>
  </div>
</template>
