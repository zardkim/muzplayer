<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { ListPlus, Repeat, Repeat1, Shuffle } from '@lucide/vue'
import { usePlayer } from '../stores/player'
import { useUi } from '../stores/ui'
import type { Track } from '../types'
import PlayerIcons from './PlayerIcons.vue'

// The icon buttons over a list of songs (album, artist, playlist, chart...): play it all, shuffle it,
// play it on repeat, add it to a playlist. Each says what it does on hover and to screen readers.
const props = withDefaults(defineProps<{ tracks: Track[]; large?: boolean; add?: boolean }>(), { add: true })
const { t } = useI18n()
const player = usePlayer()
const ui = useUi()

const empty = computed(() => !props.tracks.some((tr) => !tr.missing))
// this list is what plays now (its first song is in the queue): the repeat button shows the mode
const playingThis = computed(() => !!player.current && props.tracks.some((tr) => tr.id === player.current!.id))
const repeatOn = computed(() => playingThis.value && player.repeat !== 'off')

/** Repeat: start this list repeating; on the list already playing, step through all → one → off. */
function repeat() {
  if (playingThis.value) return player.cycleRepeat()
  player.playTracks(props.tracks, 0, { shuffle: false })
  player.repeat = 'all'
}

const box = computed(() => (props.large ? 'size-11' : 'size-[38px]'))
const icon = computed(() => (props.large ? 21 : 19))
</script>

<template>
  <span class="flex items-center gap-2">
    <button
      type="button"
      class="grid flex-none place-items-center rounded-full bg-ink text-on-ink disabled:opacity-40"
      :class="large ? 'size-12' : 'size-[42px]'"
      :disabled="empty"
      :aria-label="t('common.listenAll')"
      :title="t('common.listenAll')"
      @click="player.playTracks(tracks, 0, { shuffle: false })"
    >
      <PlayerIcons name="play" :size="large ? 20 : 17" :stroke="2" />
    </button>
    <button
      type="button"
      class="grid flex-none place-items-center rounded-full border border-line-strong hover:border-ink disabled:opacity-40"
      :class="box"
      :disabled="empty"
      :aria-label="t('common.shuffleAll')"
      :title="t('common.shuffleAll')"
      @click="player.playTracks(tracks, 0, { shuffle: true })"
    >
      <Shuffle :size="icon" :stroke-width="1.5" />
    </button>
    <button
      type="button"
      class="grid flex-none place-items-center rounded-full border hover:border-ink disabled:opacity-40"
      :class="[box, repeatOn ? 'border-accent text-accent' : 'border-line-strong']"
      :disabled="empty"
      :aria-label="repeatOn ? (player.repeat === 'one' ? t('player.repeatOne') : t('player.repeatAll')) : t('common.repeatAll')"
      :title="repeatOn ? (player.repeat === 'one' ? t('player.repeatOne') : t('player.repeatAll')) : t('common.repeatAll')"
      :aria-pressed="repeatOn"
      @click="repeat"
    >
      <Repeat1 v-if="repeatOn && player.repeat === 'one'" :size="icon" :stroke-width="1.5" />
      <Repeat v-else :size="icon" :stroke-width="1.5" />
    </button>
    <button
      v-if="add"
      type="button"
      class="grid flex-none place-items-center rounded-full border border-line-strong hover:border-ink disabled:opacity-40"
      :class="box"
      :disabled="empty"
      :aria-label="t('common.addToPlaylist')"
      :title="t('common.addToPlaylist')"
      @click="ui.playlistPicker = tracks.filter((tr) => !tr.missing)"
    >
      <ListPlus :size="icon" :stroke-width="1.5" />
    </button>
  </span>
</template>
