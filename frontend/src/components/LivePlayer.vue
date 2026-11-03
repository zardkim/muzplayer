<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { ChevronDown, Radio, Square, Volume2, VolumeX } from '@lucide/vue'
import { regionOf } from '../radio'
import { usePlayer } from '../stores/player'
import { useUi } from '../stores/ui'
import { useSwipe } from '../swipe'
import PlayerIcons from './PlayerIcons.vue'
import SeekBar from './SeekBar.vue'
import StationBadge from './StationBadge.vue'
import Marquee from './Marquee.vue'

// Full-screen player while a radio station plays (NowPlaying is the music one, BookPlayer the
// audiobook one): the logo large, play/pause, the previous/next station of the region, stop.
const { t } = useI18n()
const router = useRouter()
const player = usePlayer()
const ui = useUi()
const region = computed(() => (player.station ? regionOf(player.station, ui.views.radio) : ''))

function close() {
  ui.playerOpen = false
}
function stop() {
  player.stopStation()
  close()
}
// (a page change closes the sheet, App.vue; like the book player's link to its book)
function toList() {
  if (router.currentRoute.value.name === 'radio') close()
  else router.push({ name: 'radio' })
}

// gestures (phones): pull the player down to tuck it away; swipe the logo for the next/previous station
const scroller = ref<HTMLElement | null>(null)
const dragY = ref(0)
const logoX = ref(0)
const settling = ref(false)
function settle(apply: () => void, after?: () => void) {
  settling.value = true
  apply()
  window.setTimeout(() => {
    settling.value = false
    after?.()
  }, 300)
}
const pull = useSwipe({
  axes: ['y'],
  allow: (_, __, dy) => dy > 0 && (scroller.value?.scrollTop ?? 0) <= 0,
  move: (_, __, dy) => (dragY.value = Math.max(0, dy)),
  end: ({ dy, fast }) => {
    if (dy > 140 || (fast && dy > 40)) settle(() => (dragY.value = window.innerHeight), () => {
      close()
    })
    else settle(() => (dragY.value = 0))
  },
})
const flick = useSwipe({
  axes: ['x'],
  move: (_, dx) => (logoX.value = Math.max(-80, Math.min(80, dx * 0.5))),
  end: ({ dx, fast }) => {
    settle(() => (logoX.value = 0))
    if (Math.abs(dx) < 70 && !(fast && Math.abs(dx) > 30)) return
    player.stepStation(dx < 0 ? 1 : -1)
  },
})
</script>

<template>
  <div
    v-if="player.station"
    role="dialog"
    aria-modal="true"
    :aria-label="t('player.nowPlaying')"
    ref="scroller"
    class="fixed inset-0 z-50 overflow-y-auto bg-sheet text-ink"
    :class="[dragY ? 'overflow-hidden' : '', settling ? 'transition-transform duration-300 ease-[cubic-bezier(0.2,0.9,0.3,1)]' : '']"
    :style="dragY ? { transform: `translate3d(0,${dragY}px,0)` } : undefined"
    @touchstart="pull.onTouchstart"
    @touchmove="pull.onTouchmove"
    @touchend="pull.onTouchend"
    @touchcancel="pull.onTouchcancel"
  >
    <div
      class="relative mx-auto flex min-h-full max-w-md flex-col px-5 pt-[calc(env(safe-area-inset-top)+8px)] md:my-6 md:min-h-0 md:rounded-3xl md:shadow-2xl"
    >
      <div class="flex items-center justify-between">
        <span class="pl-1 text-[13px] font-light text-muted">{{ region ? t(`radio.region_${region}`) : '' }}</span>
        <button type="button" class="grid size-11 place-items-center rounded-full bg-bg/70" :aria-label="t('player.close')" @click="close">
          <ChevronDown :size="24" :stroke-width="1.4" />
        </button>
      </div>

      <div
        class="mt-6 flex justify-center"
        :class="settling ? 'transition-transform duration-300 ease-[cubic-bezier(0.2,0.9,0.3,1)]' : ''"
        :style="logoX ? { transform: `translateX(${logoX}px)` } : undefined"
        @touchstart="flick.onTouchstart"
        @touchmove="flick.onTouchmove"
        @touchend="flick.onTouchend"
        @touchcancel="flick.onTouchcancel"
      >
        <div class="w-[min(100%,46dvh)] shadow-[0_12px_40px_rgba(17,17,19,0.18)] rounded-2xl">
          <StationBadge :key="player.station.id" :stn="player.station.stn" :logo="player.station.logo" fill class="text-[56px]" />
        </div>
      </div>

      <div class="mt-7 flex flex-col items-center gap-1.5 text-center">
        <Marquee :text="player.station.name" class="text-[24px] font-medium leading-snug" />
        <span class="flex items-center gap-2 text-[14px] font-light text-soft">
          <span class="rounded bg-danger px-1.5 text-[11px] font-bold leading-[18px] text-white">LIVE</span>
          {{ player.playing ? t('radio.onAir') : t('radio.paused') }}
        </span>
      </div>

      <!-- live: no seek bar, a steady line instead -->
      <div class="mt-6 h-1 rounded-full bg-line">
        <div class="h-full rounded-full bg-danger transition-[width] duration-500" :class="player.playing ? 'w-full' : 'w-0'" />
      </div>

      <div class="mt-5 flex items-center justify-between px-3">
        <button type="button" class="grid size-14 place-items-center" :aria-label="t('radio.prevStation')" :title="t('radio.prevStation')" @click="player.stepStation(-1)">
          <PlayerIcons name="prev" :size="30" :stroke="1.2" />
        </button>
        <button
          type="button"
          class="grid size-[76px] place-items-center rounded-full bg-ink text-on-ink transition-transform active:scale-90"
          :aria-label="player.playing ? t('player.pause') : t('player.play')"
          @click="player.toggle()"
        >
          <PlayerIcons :name="player.playing ? 'pause' : 'play'" :size="34" :stroke="1.6" />
        </button>
        <button type="button" class="grid size-14 place-items-center" :aria-label="t('radio.nextStation')" :title="t('radio.nextStation')" @click="player.stepStation(1)">
          <PlayerIcons name="next" :size="30" :stroke="1.2" />
        </button>
      </div>

      <!-- volume: phones use their own buttons -->
      <div class="mt-6 hidden items-center gap-3 px-2 md:flex">
        <button type="button" class="grid size-9 place-items-center text-muted" :aria-label="t('player.volume')" @click="player.volume = player.volume > 0 ? 0 : 1">
          <VolumeX v-if="player.volume === 0" :size="20" :stroke-width="1.3" />
          <Volume2 v-else :size="20" :stroke-width="1.3" />
        </button>
        <div class="flex-1">
          <SeekBar :value="player.volume" :max="1" :label="t('player.volume')" fill="var(--color-ink)" @change="(v) => (player.volume = v)" @preview="(v) => v !== null && (player.volume = v)" />
        </div>
      </div>

      <div class="mt-auto grid grid-cols-2 gap-2 pb-[calc(1.25rem+env(safe-area-inset-bottom))] pt-8">
        <button type="button" class="flex h-11 items-center justify-center gap-1.5 rounded-full border border-line-strong text-[14px]" @click="toList">
          <Radio :size="16" :stroke-width="1.6" />{{ t('radio.allStations') }}
        </button>
        <button type="button" class="flex h-11 items-center justify-center gap-1.5 rounded-full border border-line-strong text-[14px]" @click="stop">
          <Square :size="14" :stroke-width="2" />{{ t('radio.stop') }}
        </button>
      </div>
    </div>
  </div>
</template>
