<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { usePlayer } from '../stores/player'
import type { Track } from '../types'
import CoverArt from './CoverArt.vue'
import LikeButton from './LikeButton.vue'
import PlayerIcons from './PlayerIcons.vue'

// Songs as artwork tiles (the songs page's cover and grid views). A tile plays the list from there.
const props = defineProps<{ tracks: Track[]; dense?: boolean }>()
const { t } = useI18n()
const player = usePlayer()
const playing = (tr: Track) => player.mode === 'music' && player.current?.id === tr.id
</script>

<template>
  <ul
    class="grid gap-x-3 gap-y-5"
    :class="dense ? 'grid-cols-3 sm:grid-cols-[repeat(auto-fill,minmax(128px,1fr))] sm:gap-x-4' : 'grid-cols-2 sm:grid-cols-[repeat(auto-fill,minmax(210px,1fr))] sm:gap-x-5'"
  >
    <li v-for="(tr, i) in props.tracks" :key="`${tr.id}-${i}`" class="group flex min-w-0 flex-col gap-2" :class="tr.missing ? 'opacity-40' : ''">
      <button type="button" class="relative block" :disabled="tr.missing" :aria-label="`${t('common.play')}: ${tr.title}`" @click="playing(tr) ? player.toggle() : player.playTracks(props.tracks, i)">
        <CoverArt :album-id="tr.album_id" :has-cover="tr.has_cover" :version="tr.cover_v" :rounded="dense ? 'rounded-lg' : 'rounded-xl'" />
        <span
          class="absolute inset-0 grid place-items-center rounded-[inherit] bg-black/25 transition-opacity"
          :class="playing(tr) ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'"
        >
          <span class="grid place-items-center rounded-full bg-white/90 text-ink" :class="dense ? 'size-9' : 'size-12'">
            <PlayerIcons :name="playing(tr) && player.playing ? 'pause' : 'play'" :size="dense ? 16 : 20" :stroke="1.8" />
          </span>
        </span>
      </button>
      <span class="flex min-w-0 items-start gap-1">
        <span class="flex min-w-0 flex-1 flex-col">
          <span class="truncate" :class="[dense ? 'text-[14px]' : 'text-base', playing(tr) ? 'text-accent' : '']">{{ tr.title }}</span>
          <span class="truncate font-light text-muted" :class="dense ? 'text-[12px]' : 'text-sm'">{{ tr.artist || t('common.unknownArtist') }}</span>
        </span>
        <LikeButton v-if="!dense" :track="tr" :size="18" box="size-8 -mt-1" />
      </span>
    </li>
  </ul>
</template>
