<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { Pause, Play, Repeat, Repeat1, Shuffle, SkipBack, SkipForward } from '@lucide/vue'
import { usePlayer } from '../stores/player'

defineProps<{ large?: boolean }>()
const { t } = useI18n()
const player = usePlayer()
const repeatLabel = () =>
  player.repeat === 'one' ? t('player.repeatOne') : player.repeat === 'all' ? t('player.repeatAll') : t('player.repeatOff')
</script>

<template>
  <div class="flex items-center" :class="large ? 'w-full justify-between' : 'gap-2'">
    <button
      type="button"
      class="grid place-items-center"
      :class="[large ? 'size-12' : 'size-11', player.shuffle ? 'text-accent' : 'text-muted hover:text-ink']"
      :aria-label="player.shuffle ? t('player.shuffleOn') : t('player.shuffleOff')"
      :aria-pressed="player.shuffle"
      @click="player.toggleShuffle()"
    >
      <Shuffle :size="large ? 22 : 18" />
    </button>
    <button type="button" class="grid place-items-center text-ink" :class="large ? 'size-14' : 'size-11'" :aria-label="t('player.prev')" @click="player.prev()">
      <SkipBack :size="large ? 30 : 22" fill="currentColor" />
    </button>
    <button
      type="button"
      class="grid place-items-center rounded-full bg-ink text-bg transition-transform active:scale-95"
      :class="large ? 'size-[76px]' : 'size-12'"
      :aria-label="player.playing ? t('player.pause') : t('player.play')"
      @click="player.toggle()"
    >
      <Pause v-if="player.playing" :size="large ? 30 : 20" fill="currentColor" />
      <Play v-else :size="large ? 30 : 20" fill="currentColor" class="translate-x-[2px]" />
    </button>
    <button type="button" class="grid place-items-center text-ink" :class="large ? 'size-14' : 'size-11'" :aria-label="t('player.next')" @click="player.next()">
      <SkipForward :size="large ? 30 : 22" fill="currentColor" />
    </button>
    <button
      type="button"
      class="grid place-items-center"
      :class="[large ? 'size-12' : 'size-11', player.repeat !== 'off' ? 'text-accent' : 'text-muted hover:text-ink']"
      :aria-label="repeatLabel()"
      @click="player.cycleRepeat()"
    >
      <Repeat1 v-if="player.repeat === 'one'" :size="large ? 22 : 18" />
      <Repeat v-else :size="large ? 22 : 18" />
    </button>
  </div>
</template>
