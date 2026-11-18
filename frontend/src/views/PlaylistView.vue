<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ArrowLeftRight, ChevronDown, FileDown, ListMusic, Pencil, Plus, RefreshCw, SlidersHorizontal, Trash2, Users, X, Zap } from '@lucide/vue'
import { api } from '../api'
import { errorMessage } from '../i18n'
import { useLibrary } from '../stores/library'
import { useUi } from '../stores/ui'
import type { Playlist, PlaylistDetail } from '../types'
import BaseModal from '../components/BaseModal.vue'
import DownloadButton from '../components/DownloadButton.vue'
import PageHeader from '../components/PageHeader.vue'
import PlayActions from '../components/PlayActions.vue'
import PlaylistTransferSheet from '../components/PlaylistTransferSheet.vue'
import SearchAddSheet from '../components/SearchAddSheet.vue'
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
const adding = ref(false) // the search-and-add sheet
const smart = computed(() => playlist.value?.kind === 'smart')
// songs copied or moved into another of my playlists: those picked in the list, else all (ticked in the sheet)
const transfer = ref<number[] | null>(null)

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

// my own ordinary list made shared (everyone sees it), or a shared one made its owner's alone again
const canShare = computed(() => !!playlist.value && playlist.value.can_edit && !smart.value && !playlist.value.is_default)
async function toggleShared() {
  const p = playlist.value
  if (!p) return
  const shared = !p.is_shared
  if (!confirm(t(shared ? 'playlists.shareConfirm' : 'playlists.unshareConfirm', { name: p.name }))) return
  await run(() => api(`/playlists/${props.id}`, { method: 'PATCH', body: { shared } }))
  ui.notify(t(shared ? 'playlists.shared' : 'playlists.unshared'))
}

// an imported file's songs not found: kept, looked for again after each scan or now
const missingOpen = ref(false)
async function rematch() {
  try {
    const r = await api<{ found: number; left: number }>(`/playlists/${props.id}/missing/rematch`, { method: 'POST' })
    ui.notify(t('playlists.rematched', r))
  } catch (e) {
    ui.notify(errorMessage(e), true)
  }
  await load()
  library.loadPlaylists().catch(() => {})
}
function forget(id?: number) {
  if (id === undefined && !confirm(t('playlists.forgetAllConfirm'))) return
  run(() => api(`/playlists/${props.id}/missing${id === undefined ? '' : `/${id}`}`, { method: 'DELETE' }))
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
    <PageHeader :title="playlist.name" :icon="smart ? Zap : ListMusic" :sub="[playlist.is_shared ? t('shared.badge') : '', smart ? t('smart.badge') : '', t('common.tracks', playlist.entries.length)].filter(Boolean).join(' · ')" />
    <div class="flex flex-wrap gap-2">
      <PlayActions :tracks="tracks" :add="false" />
      <!-- someone else's shared list: listen, or copy it into one's own -->
      <button v-if="!playlist.can_edit" type="button" class="h-[38px] rounded-full border border-line-strong px-4 text-[15px] disabled:opacity-40" :disabled="!tracks.length" @click="ui.playlistPicker = tracks">{{ t('charts.copyToPlaylist') }}</button>
      <button v-if="!smart && playlist.can_edit" type="button" class="flex h-[38px] items-center gap-1.5 rounded-full bg-ink px-4 text-[15px] text-on-ink" @click="adding = true">
        <Plus :size="16" :stroke-width="1.8" />{{ t('playlists.addSongsButton') }}
      </button>
      <button v-if="smart && playlist.can_edit" type="button" class="flex h-[38px] items-center gap-1.5 rounded-full border border-line-strong px-4 text-[15px]" @click="editingRules = true">
        <SlidersHorizontal :size="15" :stroke-width="1.5" />{{ t('smart.edit') }}
      </button>
      <button v-if="!smart && playlist.can_edit && tracks.length" type="button" class="flex h-[38px] items-center gap-1.5 rounded-full border border-line-strong px-4 text-[15px]" @click="transfer = []">
        <ArrowLeftRight :size="15" :stroke-width="1.6" />{{ t('transfer.title') }}
      </button>
      <DownloadButton v-if="tracks.length" class="h-[38px]" :list="saveAs" />
      <button v-if="smart" type="button" class="h-[38px] rounded-full border border-line-strong px-4 text-[15px] disabled:opacity-40" :disabled="!tracks.length" @click="snapshot">{{ t('common.saveAsPlaylist') }}</button>
      <button v-else-if="playlist.can_edit" type="button" class="grid size-[38px] place-items-center rounded-full border border-line-strong" :aria-label="t('common.rename')" @click="(newName = playlist.name), (renaming = true)">
        <Pencil :size="16" :stroke-width="1.4" />
      </button>
      <button
        v-if="canShare && (playlist.is_shared || !playlist.chart_id)"
        type="button"
        class="grid size-[38px] place-items-center rounded-full border border-line-strong"
        :class="playlist.is_shared ? 'bg-ink text-on-ink' : ''"
        :aria-label="t(playlist.is_shared ? 'playlists.unshare' : 'playlists.share')"
        :title="t(playlist.is_shared ? 'playlists.unshare' : 'playlists.share')"
        :aria-pressed="!!playlist.is_shared"
        @click="toggleShared"
      >
        <Users :size="16" :stroke-width="1.5" />
      </button>
      <a
        v-if="tracks.length"
        :href="`/api/v1/playlists/${playlist.id}/export`"
        download
        class="grid size-[38px] place-items-center rounded-full border border-line-strong"
        :aria-label="t('playlists.export')"
        :title="t('playlists.export')"
      >
        <FileDown :size="16" :stroke-width="1.5" />
      </a>
      <button v-if="!playlist.is_default && playlist.can_edit" type="button" class="grid size-[38px] place-items-center rounded-full border border-line-strong text-danger" :aria-label="t('common.delete')" @click="destroy">
        <Trash2 :size="16" :stroke-width="1.4" />
      </button>
    </div>
    <p v-if="!tracks.length" class="font-light text-muted">{{ smart ? t('common.empty') : t('playlists.emptyTracks') }}</p>
    <TrackList :tracks="tracks" :editable="!smart && playlist.can_edit" @remove="remove" @move="move" @transfer="(ix) => (transfer = ix.map((i) => playlist!.entries[i].entry_id!))" />
    <!-- an imported file's songs not in the library (yet) -->
    <section v-if="playlist.can_edit && playlist.missing?.length" class="flex flex-col gap-2 rounded-2xl border border-line p-4">
      <div class="flex flex-wrap items-center gap-2">
        <button type="button" class="flex flex-1 items-center gap-2 text-left text-[16px] font-medium" :aria-expanded="missingOpen" @click="missingOpen = !missingOpen">
          <ChevronDown :size="17" :stroke-width="1.7" class="transition-transform" :class="missingOpen ? '' : '-rotate-90'" />
          <span class="text-danger">{{ t('playlists.missingTitle', { n: playlist.missing.length }) }}</span>
        </button>
        <button type="button" class="flex h-9 items-center gap-1.5 rounded-full border border-line-strong px-3.5 text-[14px] hover:border-ink" @click="rematch">
          <RefreshCw :size="15" :stroke-width="1.6" />{{ t('playlists.rematch') }}
        </button>
        <button type="button" class="h-9 rounded-full px-3 text-[14px] text-muted hover:text-danger" @click="forget()">{{ t('playlists.forgetAll') }}</button>
      </div>
      <p class="text-[13px] font-light text-muted">{{ t('playlists.missingHelp') }}</p>
      <ul v-if="missingOpen" class="flex flex-col">
        <li v-for="m in playlist.missing" :key="m.id" class="flex items-center gap-2 border-t border-line py-2">
          <span class="flex min-w-0 flex-1 flex-col">
            <span class="truncate text-[14px]">{{ m.label }}</span>
            <span class="truncate text-[12px] text-muted" :title="m.path">{{ m.path }}</span>
          </span>
          <button type="button" class="grid size-8 flex-none place-items-center rounded-full text-muted hover:bg-surface hover:text-ink" :aria-label="t('playlists.forget')" :title="t('playlists.forget')" @click="forget(m.id)">
            <X :size="16" :stroke-width="1.6" />
          </button>
        </li>
      </ul>
    </section>
    <PlaylistTransferSheet
      v-if="transfer"
      kind="music"
      :source-id="playlist.id"
      :items="playlist.entries.map((e) => ({ entry: e.entry_id!, title: e.track.title, sub: e.track.artist ?? '' }))"
      :picked="transfer"
      @close="transfer = null"
      @done="load"
    />
    <SearchAddSheet
      v-if="adding"
      kind="tracks"
      :list-id="playlist.id"
      :list-name="playlist.name"
      :has="tracks.map((x) => x.id)"
      @added="load(), library.loadPlaylists().catch(() => {})"
      @close="adding = false"
    />
    <SmartRulesSheet v-if="editingRules" :playlist="playlist" @close="editingRules = false" @saved="rulesSaved" />

    <BaseModal v-if="renaming" :title="t('common.rename')" @close="renaming = false">
      <form class="flex flex-col gap-4" @submit.prevent="rename">
        <label class="flex flex-col gap-1.5 text-[13px] text-muted">
          {{ t('playlists.name') }}
          <input v-model="newName" maxlength="200" class="field h-12 px-4" />
        </label>
        <button type="submit" class="h-12 rounded-full bg-ink text-on-ink disabled:opacity-40" :disabled="!newName.trim()">{{ t('common.save') }}</button>
      </form>
    </BaseModal>
  </div>
</template>
