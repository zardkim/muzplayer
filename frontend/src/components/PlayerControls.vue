<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { Repeat, Repeat1, Shuffle } from '@lucide/vue'
import { usePlayer } from '../stores/player'
import PlayerIcons from './PlayerIcons.vue'

defineProps<{ large?: boolean }>()
const { t } = useI18n()
const player = usePlayer()
const repeatLabel = () =>
  player.repeat === 'one' ? t('player.repeatOne') : player.repeat === 'all' ? t('player.repeatAll') : t('player.repeatOff')
</script>

<template>
  <div class="flex items-center" :class="large ? 'w-full justify-between' : 'gap-1'">
    <button
      type="button"
      class="grid place-items-center"
      :class="[large ? 'size-[52px]' : 'size-11', player.repeat !== 'off' ? 'text-accent' : 'text-ink']"
      :aria-label="repeatLabel()"
      @click="player.cycleRepeat()"
    >
      <Repeat1 v-if="player.repeat === 'one'" :size="large ? 28 : 20" :stroke-width="1.2" />
      <Repeat v-else :size="large ? 28 : 20" :stroke-width="1.2" />
    </button>
    <button type="button" class="grid place-items-center text-ink" :class="large ? 'size-14' : 'size-11'" :aria-label="t('player.prev')" @click="player.prev()">
      <PlayerIcons name="prev" :size="large ? 32 : 24" :stroke="1.2" />
    </button>
    <button
      type="button"
      class="grid place-items-center text-ink transition-transform active:scale-90"
      :class="large ? 'size-[72px]' : 'size-12'"
      :aria-label="player.playing ? t('player.pause') : t('player.play')"
      @click="player.toggle()"
    >
      <PlayerIcons :name="player.playing ? 'pause' : 'play'" :size="large ? 42 : 30" :stroke="large ? 1.2 : 1.5" />
    </button>
    <button type="button" class="grid place-items-center text-ink" :class="large ? 'size-14' : 'size-11'" :aria-label="t('player.next')" @click="player.next()">
      <PlayerIcons name="next" :size="large ? 32 : 24" :stroke="1.2" />
    </button>
    <button
      type="button"
      class="grid place-items-center"
      :class="[large ? 'size-[52px]' : 'size-11', player.shuffle ? 'text-accent' : 'text-ink']"
      :aria-label="player.shuffle ? t('player.shuffleOn') : t('player.shuffleOff')"
      :aria-pressed="player.shuffle"
      @click="player.toggleShuffle()"
    >
      <Shuffle :size="large ? 28 : 20" :stroke-width="1.2" />
    </button>
  </div>
</template>
