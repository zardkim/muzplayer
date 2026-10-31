<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { MUSIC_SPEEDS, usePlayer } from '../stores/player'

// music playback speed (Settings → music speed): each tap steps to the next speed, round to 0.75×
const { t } = useI18n()
const player = usePlayer()
function next() {
  const i = MUSIC_SPEEDS.indexOf(player.musicRate)
  player.musicRate = MUSIC_SPEEDS[(i + 1) % MUSIC_SPEEDS.length]
}
</script>

<template>
  <button
    type="button"
    class="h-8 rounded-full border px-2.5 font-display text-[13px]"
    :class="player.musicRate === 1 ? 'border-line-strong' : 'border-accent text-accent'"
    :aria-label="t('player.speed')"
    :title="t('player.speed')"
    @click="next"
  >
    {{ player.musicRate }}×
  </button>
</template>
