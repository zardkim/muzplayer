<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ArrowDownToLine, ArrowUpFromLine, ChevronLeft, Monitor, Smartphone } from '@lucide/vue'
import { duration } from '../format'
import { errorMessage } from '../i18n'
import { usePlayer } from '../stores/player'
import { useRemote, type RemoteDevice } from '../stores/remote'
import { useUi } from '../stores/ui'
import BaseModal from './BaseModal.vue'
import CastTargets from './CastTargets.vue'
import CoverArt from './CoverArt.vue'
import PlayerIcons from './PlayerIcons.vue'
import SeekBar from './SeekBar.vue'

// Devices: this one, the person's other open muzplayer devices (remote.ts: watch, control, move the
// queue between them), and Chromecast / AirPlay (CastTargets).
const { t } = useI18n()
const ui = useUi()
const player = usePlayer()
const remote = useRemote()

const now = ref(Date.now()) // moves the other device's position on between its reports
let timer = 0
onMounted(() => (timer = window.setInterval(() => (now.value = Date.now()), 1000)))
onUnmounted(() => window.clearInterval(timer))

const d = computed(() => remote.targetDevice)
const pos = computed(() => (now.value, d.value ? remote.positionOf(d.value) : 0))
const phone = (x: RemoteDevice) => /iPhone|iPad|Android/.test(x.name)

async function send(cmd: string, arg?: unknown) {
  try {
    await remote.command(d.value!.id, cmd, arg)
  } catch (e) {
    ui.notify(errorMessage(e), true)
  }
}
async function move(fn: () => Promise<void>) {
  try {
    await fn()
  } catch (e) {
    ui.notify(errorMessage(e), true)
  }
}
</script>

<template>
  <BaseModal :title="t('devices.title')" @close="ui.devicesOpen = false">
    <!-- one device, controlled from here -->
    <div v-if="d" class="flex flex-col gap-4">
      <button type="button" class="flex items-center gap-1 self-start text-[14px] text-muted" @click="remote.target = null">
        <ChevronLeft :size="16" :stroke-width="1.6" />{{ t('devices.all') }}
      </button>
      <div class="flex items-center gap-3.5">
        <CoverArt :album-id="d.state?.track?.album_id ?? null" :has-cover="!!d.state?.track?.has_cover" :version="d.state?.track?.cover_v" rounded="rounded-lg" class="size-16 flex-none" />
        <div class="flex min-w-0 flex-col">
          <span class="text-[13px] text-accent">{{ d.name }}</span>
          <span class="truncate text-[17px] font-medium">{{ d.state?.track?.title ?? t('devices.idle') }}</span>
          <span class="truncate text-sm font-light text-muted">{{ d.state?.track?.artist }}</span>
        </div>
      </div>
      <p v-if="d.state?.blocked" class="rounded-xl bg-accent-soft px-3.5 py-2.5 text-[13px]">{{ t('devices.blocked') }}</p>
      <template v-if="d.state?.track">
        <div class="flex items-center gap-2.5 font-display text-xs text-muted">
          <span class="w-9 text-right">{{ duration(pos) }}</span>
          <SeekBar :value="pos" :max="d.state.duration || d.state.track.duration || 0" :label="t('player.seek')" @change="(v) => send('seek', v)" />
          <span class="w-9">{{ duration(d.state.duration || d.state.track.duration || 0) }}</span>
        </div>
        <div class="flex items-center justify-center gap-6">
          <button type="button" class="grid size-12 place-items-center" :aria-label="t('player.prev')" @click="send('prev')"><PlayerIcons name="prev" :size="26" :stroke="1.3" /></button>
          <button type="button" class="grid size-14 place-items-center rounded-full bg-ink text-on-ink" :aria-label="d.state.playing ? t('player.pause') : t('player.play')" @click="send('toggle')">
            <PlayerIcons :name="d.state.playing ? 'pause' : 'play'" :size="24" :stroke="1.6" />
          </button>
          <button type="button" class="grid size-12 place-items-center" :aria-label="t('player.next')" @click="send('next')"><PlayerIcons name="next" :size="26" :stroke="1.3" /></button>
        </div>
        <label v-if="d.state.canVolume" class="flex items-center gap-3 text-[13px] text-muted">
          <span class="flex-none whitespace-nowrap">{{ t('player.volume') }}</span>
          <SeekBar :value="d.state.volume" :max="1" :label="t('player.volume')" fill="var(--color-ink)" @change="(v) => send('volume', v)" />
        </label>
      </template>
      <div class="flex flex-wrap gap-2">
        <button v-if="d.state?.track" type="button" class="flex h-10 items-center gap-1.5 rounded-full border border-line-strong px-4 text-[14px]" @click="move(() => remote.takeOver(d!.id))">
          <ArrowDownToLine :size="16" :stroke-width="1.5" />{{ t('devices.takeOver') }}
        </button>
        <button v-if="player.current && player.mode === 'music'" type="button" class="flex h-10 items-center gap-1.5 rounded-full border border-line-strong px-4 text-[14px]" @click="move(() => remote.sendQueue(d!.id))">
          <ArrowUpFromLine :size="16" :stroke-width="1.5" />{{ t('devices.sendHere') }}
        </button>
      </div>
    </div>

    <!-- the list -->
    <div v-else class="flex flex-col gap-1">
      <div class="flex items-center gap-3.5 py-2.5">
        <component :is="/iPhone|iPad|Android/.test(remote.name) ? Smartphone : Monitor" :size="24" :stroke-width="1.3" class="text-accent" />
        <span class="flex min-w-0 flex-col">
          <span class="text-[16px]">{{ remote.name }} <span class="text-[13px] text-accent">· {{ t('devices.thisOne') }}</span></span>
          <span class="truncate text-sm font-light text-muted">{{ player.current && player.mode === 'music' ? `${player.current.title} — ${player.current.artist}` : t('devices.idle') }}</span>
        </span>
      </div>
      <button v-for="x in remote.devices" :key="x.id" type="button" class="flex items-center gap-3.5 rounded-xl py-2.5 text-left hover:bg-surface" @click="remote.target = x.id">
        <component :is="phone(x) ? Smartphone : Monitor" :size="24" :stroke-width="1.3" />
        <span class="flex min-w-0 flex-1 flex-col">
          <span class="text-[16px]">{{ x.name }}</span>
          <span class="truncate text-sm font-light text-muted">
            <template v-if="x.state?.track">{{ x.state.playing ? '▶ ' : '' }}{{ x.state.track.title }} — {{ x.state.track.artist }}</template>
            <template v-else>{{ t('devices.idle') }}</template>
          </span>
        </span>
      </button>
      <p v-if="!remote.devices.length" class="py-2 text-[14px] font-light text-muted">{{ remote.connected ? t('devices.none') : t('devices.offline') }}</p>
      <CastTargets />
    </div>
  </BaseModal>
</template>
