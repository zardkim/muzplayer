<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { Volume1, Volume2, VolumeX } from '@lucide/vue'
import { usePlayer } from '../stores/player'
import SeekBar from './SeekBar.vue'

// PC player bar: the speaker. Pointing at it (or focusing it) shows the volume as a slider going
// up; a click mutes and brings the sound back; the wheel over it turns it up or down.
const { t } = useI18n()
const player = usePlayer()
const open = ref(false)
let closing: number | undefined
function show() {
  clearTimeout(closing)
  open.value = true
}
function hide() {
  clearTimeout(closing)
  closing = window.setTimeout(() => (open.value = false), 250)
}

let before = 1 // the volume before muting
function mute() {
  if (player.volume > 0) {
    before = player.volume
    player.volume = 0
  } else player.volume = before || 1
}
function wheel(e: WheelEvent) {
  player.volume = Math.min(1, Math.max(0, Math.round((player.volume - Math.sign(e.deltaY) * 0.05) * 100) / 100))
}
</script>

<template>
  <div class="relative" @mouseenter="show" @mouseleave="hide" @focusin="show" @focusout="hide" @wheel.prevent="wheel">
    <button type="button" class="grid size-10 place-items-center rounded-full hover:bg-surface" :aria-label="t('player.volume')" :title="t('player.volume')" @click="mute">
      <VolumeX v-if="player.volume === 0" :size="20" :stroke-width="1.3" />
      <Volume1 v-else-if="player.volume < 0.5" :size="20" :stroke-width="1.3" />
      <Volume2 v-else :size="20" :stroke-width="1.3" />
    </button>
    <!-- above the speaker (the padding keeps the pointer inside on its way up) -->
    <div v-if="open" class="absolute bottom-full left-1/2 z-10 -translate-x-1/2 pb-2">
      <div class="glass flex h-40 w-11 flex-col items-center gap-1 rounded-full pb-3 pt-2.5">
        <span class="font-display text-[11px] text-muted">{{ Math.round(player.volume * 100) }}</span>
        <div class="relative w-full flex-1">
          <div class="absolute left-1/2 top-1/2 w-[104px] -translate-x-1/2 -translate-y-1/2 -rotate-90">
            <SeekBar :value="player.volume" :max="1" :label="t('player.volume')" fill="var(--color-ink)" @change="(v) => (player.volume = v)" @preview="(v) => v !== null && (player.volume = v)" />
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
