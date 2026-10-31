<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ChevronDown, Trash2 } from '@lucide/vue'
import { canSave, offline, removeList, savedBytes, type SavedList } from '../offline'
import { usePlayer } from '../stores/player'
import CoverArt from '../components/CoverArt.vue'
import PageHeader from '../components/PageHeader.vue'
import PlayerIcons from '../components/PlayerIcons.vue'
import TrackList from '../components/TrackList.vue'

// Albums and playlists saved on this device (offline.ts): everything here comes from the device,
// so it works without a connection.
const { t } = useI18n()
const player = usePlayer()
const open = ref<string | null>(null)

const mb = (bytes: number) => Math.round(bytes / 1024 / 1024)
const listBytes = (l: SavedList) => l.tracks.reduce((n, x) => n + (offline.files[x.id] ?? 0), 0)

function remove(l: SavedList) {
  if (confirm(t('offline.removeConfirm', { name: l.title }))) void removeList(l.key)
}
</script>

<template>
  <div class="flex flex-col gap-6">
    <PageHeader :title="t('offline.title')" />
    <p class="text-[14px] font-light text-muted">
      {{ canSave() ? t('offline.help', { mb: mb(savedBytes()) }) : t('offline.unsupported') }}
    </p>
    <p v-if="canSave() && !offline.lists.length" class="font-light text-muted">{{ t('offline.empty') }}</p>

    <section v-for="l in offline.lists" :key="l.key" class="flex flex-col gap-2">
      <div class="flex items-center gap-3.5">
        <CoverArt :album-id="l.cover?.albumId ?? null" :has-cover="!!l.cover?.hasCover" :version="l.cover?.v" rounded="rounded-lg" class="size-[56px] flex-none" />
        <RouterLink :to="l.link" class="flex min-w-0 flex-1 flex-col">
          <span class="truncate text-[17px]">{{ l.title }}</span>
          <span class="truncate text-sm font-light text-muted">
            {{ l.subtitle ? `${l.subtitle} · ` : '' }}{{ t('common.tracks', l.tracks.length) }} · {{ mb(listBytes(l)) }} MB
            <template v-if="offline.progress[l.key]"> · {{ t('offline.saving', offline.progress[l.key]) }}</template>
          </span>
        </RouterLink>
        <button type="button" class="grid size-10 flex-none place-items-center rounded-full bg-ink text-on-ink" :aria-label="t('common.listenAll')" @click="player.playTracks(l.tracks, 0, { shuffle: false })">
          <PlayerIcons name="play" :size="15" :stroke="1.8" />
        </button>
        <button type="button" class="grid size-10 flex-none place-items-center rounded-full border border-line-strong" :aria-label="t('offline.showTracks')" :aria-expanded="open === l.key" @click="open = open === l.key ? null : l.key">
          <ChevronDown :size="18" :stroke-width="1.5" :class="open === l.key ? 'rotate-180' : ''" />
        </button>
        <button type="button" class="grid size-10 flex-none place-items-center rounded-full border border-line-strong text-danger" :aria-label="t('offline.remove')" @click="remove(l)">
          <Trash2 :size="17" :stroke-width="1.5" />
        </button>
      </div>
      <TrackList v-if="open === l.key" :tracks="l.tracks" :show-album="!l.key.startsWith('album:')" />
    </section>
  </div>
</template>
