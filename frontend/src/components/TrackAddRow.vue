<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { Check, Plus } from '@lucide/vue'
import type { Track } from '../types'
import CoverArt from './CoverArt.vue'

// A song in the "add songs" sheet (SearchAddSheet): its + adds it; one in the list already shows a check.
defineProps<{ track: Track; added: boolean }>()
const emit = defineEmits<{ add: [] }>()
const { t } = useI18n()
</script>

<template>
  <li class="flex items-center gap-3 rounded-xl px-2 py-1.5 hover:bg-surface">
    <CoverArt :album-id="track.album_id" :has-cover="track.has_cover" :version="track.cover_v" rounded="rounded-md" class="size-11 flex-none" />
    <span class="flex min-w-0 flex-1 flex-col">
      <span class="truncate text-[15px]">{{ track.title }}</span>
      <span class="truncate text-[13px] text-muted">{{ track.artist || t('common.unknownArtist') }} · {{ track.album || t('common.unknownAlbum') }}</span>
    </span>
    <span v-if="added" class="grid size-10 flex-none place-items-center text-accent" :aria-label="t('playlists.inList')"><Check :size="20" :stroke-width="2" /></span>
    <button v-else type="button" class="grid size-10 flex-none place-items-center rounded-full border border-line-strong hover:border-ink" :aria-label="`${t('common.add')}: ${track.title}`" @click="emit('add')">
      <Plus :size="18" :stroke-width="1.8" />
    </button>
  </li>
</template>
