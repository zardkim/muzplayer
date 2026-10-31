<script setup lang="ts">
import { onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { Airplay, Cast } from '@lucide/vue'
import { castControl, castQueue, castState, castSupported, loadCast } from '../cast'
import { duration } from '../format'
import { usePlayer } from '../stores/player'
import { useUi } from '../stores/ui'
import PlayerIcons from './PlayerIcons.vue'
import SeekBar from './SeekBar.vue'

// Chromecast (cast.ts; Chrome on a PC or Android) and AirPlay (Safari's own picker) in the devices sheet.
const { t } = useI18n()
const ui = useUi()
const player = usePlayer()
onMounted(loadCast)

async function start() {
  if (!player.current || player.mode !== 'music') return ui.notify(t('devices.castNothing'), true)
  try {
    await castQueue(player.queue, player.index, player.currentTime)
    if (player.playing) player.toggle() // it plays on the Cast device now
  } catch (e) {
    if ((e as { code?: string })?.code !== 'cancel' && e !== 'cancel') ui.notify(t('devices.castFailed'), true)
  }
}
</script>

<template>
  <div class="mt-3 flex flex-col gap-1 border-t border-line pt-3">
    <!-- Chromecast -->
    <template v-if="castState.active">
      <div class="flex items-center gap-3.5 py-2">
        <Cast :size="24" :stroke-width="1.3" class="text-accent" />
        <span class="flex min-w-0 flex-1 flex-col">
          <span class="text-[16px]">{{ castState.name || 'Chromecast' }}</span>
          <span class="truncate text-sm font-light text-muted">{{ castState.title ? `${castState.title} — ${castState.artist}` : t('devices.idle') }}</span>
        </span>
        <button type="button" class="h-9 rounded-full border border-line-strong px-3.5 text-[13px]" @click="castControl.stop()">{{ t('devices.castStop') }}</button>
      </div>
      <div class="flex items-center gap-2.5 font-display text-xs text-muted">
        <span class="w-9 text-right">{{ duration(castState.position) }}</span>
        <SeekBar :value="castState.position" :max="castState.duration" :label="t('player.seek')" @change="castControl.seek" />
        <span class="w-9">{{ duration(castState.duration) }}</span>
      </div>
      <div class="flex items-center justify-center gap-6">
        <button type="button" class="grid size-12 place-items-center" :aria-label="t('player.prev')" @click="castControl.prev()"><PlayerIcons name="prev" :size="24" :stroke="1.3" /></button>
        <button type="button" class="grid size-12 place-items-center rounded-full bg-ink text-on-ink" :aria-label="castState.playing ? t('player.pause') : t('player.play')" @click="castControl.toggle()">
          <PlayerIcons :name="castState.playing ? 'pause' : 'play'" :size="22" :stroke="1.6" />
        </button>
        <button type="button" class="grid size-12 place-items-center" :aria-label="t('player.next')" @click="castControl.next()"><PlayerIcons name="next" :size="24" :stroke="1.3" /></button>
      </div>
      <label class="flex items-center gap-3 text-[13px] text-muted">
        <span class="flex-none whitespace-nowrap">{{ t('player.volume') }}</span>
        <SeekBar :value="castState.volume" :max="1" :label="t('player.volume')" fill="var(--color-ink)" @change="castControl.volume" />
      </label>
    </template>
    <button v-else-if="castState.ready && castState.devices" type="button" class="flex items-center gap-3.5 rounded-xl py-2.5 text-left hover:bg-surface" @click="start">
      <Cast :size="24" :stroke-width="1.3" />
      <span class="flex flex-col"><span class="text-[16px]">Chromecast</span><span class="text-sm font-light text-muted">{{ t('devices.castStart') }}</span></span>
    </button>
    <p v-else-if="castSupported()" class="py-1 text-[13px] font-light text-muted">{{ t('devices.castNone') }}</p>

    <!-- AirPlay (Safari) -->
    <button v-if="player.airplay" type="button" class="flex items-center gap-3.5 rounded-xl py-2.5 text-left hover:bg-surface" @click="player.showAirPlay()">
      <Airplay :size="24" :stroke-width="1.3" />
      <span class="flex flex-col"><span class="text-[16px]">AirPlay</span><span class="text-sm font-light text-muted">{{ t('devices.airplayHelp') }}</span></span>
    </button>
  </div>
</template>
