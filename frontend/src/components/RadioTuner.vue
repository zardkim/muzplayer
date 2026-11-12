<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { AudioWaveform, ChevronDown, ChevronRight, Share2, Star, Volume1, Volume2 } from '@lucide/vue'
import { vLongPress } from '../longPress'
import { onAirText, useOnAir } from '../radio'
import { usePlayer } from '../stores/player'
import { useUi } from '../stores/ui'
import { BANDS, bandOf, dialFor, nextStop, stepOf, tickLabel, type Band } from '../tuner'
import { setNoise, stopNoise, wakeNoise } from '../tunerNoise'
import type { RadioStation } from '../types'
import PlayerIcons from './PlayerIcons.vue'
import StationBadge from './StationBadge.vue'

// The Radio page's tuner (docs/radio_tuner_plan.md): the region's stations on a dial by frequency, like
// a phone's FM radio. The dial slides under a fixed needle (dragged, flung, tapped, the wheel, the
// arrow keys); where it stops on a station, that station plays a moment later; between stations, the
// radio stops. ◀◀ ▶▶ seek the next station (held: SCAN, seven seconds each until a tap). The station
// playing moves the dial to it. Shown with it: what it has on air (radio_now.py), when known.
const props = defineProps<{ stations: RadioStation[]; regions: string[] }>()
const region = defineModel<string>('region', { required: true })
const emit = defineEmits<{ list: [] }>()
const { t } = useI18n()
const player = usePlayer()
const ui = useUi()

const live = computed(() => (player.mode === 'live' ? player.station : null))
const inRegion = computed(() => props.stations.filter((s) => s.regions.includes(region.value) || s.custom))
const bands = computed(() => BANDS.filter((b) => inRegion.value.some((s) => bandOf(s, region.value) === b)))
const band = ref<Band>('FM')
const dial = computed(() => dialFor(inRegion.value, region.value, band.value))

// where the needle is, in steps (a fraction while moving)
const pos = ref(0)
const step = computed(() => Math.max(0, Math.min(dial.value.steps - 1, Math.round(pos.value))))
const here = computed(() => dial.value.stops.find((s) => s.step === step.value)?.stations ?? [])
const pickedAlt = ref(0) // two stations on one frequency: which one
const station = computed(() => here.value[Math.min(pickedAlt.value, here.value.length - 1)] ?? null)
const channel = computed(() => {
  const i = dial.value.stops.findIndex((s) => s.step === step.value)
  return i < 0 ? null : String(i + 1).padStart(2, '0')
})

/** The dial at a station's place (its band too), without tuning it again. */
function showStation(st: RadioStation | null) {
  if (!st || !inRegion.value.some((s) => s.id === st.id)) return false
  band.value = bandOf(st, region.value)
  const at = stepOf(dial.value, st.id)
  if (at === null) return false
  stopMotion()
  pos.value = at
  const stop = dial.value.stops.find((s) => s.step === at)
  pickedAlt.value = Math.max(0, stop?.stations.findIndex((s) => s.id === st.id) ?? 0)
  return true
}
function start() {
  if (showStation(live.value)) return
  band.value = bands.value.includes(band.value) ? band.value : bands.value[0] ?? 'FM'
  pos.value = dial.value.stops[0]?.step ?? 0
}
onMounted(start)
watch(region, start)
// the station changed elsewhere (the mini player's next station, the list): the dial follows
watch(() => live.value?.id, (id) => {
  if (id && id !== station.value?.id) showStation(live.value)
})
function pickBand(b: Band) {
  if (b === band.value) return
  band.value = b
  pickedAlt.value = 0
  pos.value = dial.value.stops[0]?.step ?? 0
  settle()
}

// ---- tuning: a moment after the dial rests ----
let tuneTimer = 0
function settle() {
  window.clearTimeout(tuneTimer)
  tuneTimer = window.setTimeout(tune, 400)
}
function tune() {
  const st = station.value
  if (st) {
    if (live.value?.id !== st.id) player.playStation(st)
  } else if (live.value) {
    player.stopStation() // between stations: silence
  }
}
function toggle() {
  const st = station.value
  if (!st) return
  if (live.value?.id === st.id) player.toggle()
  else player.playStation(st)
}

// ---- moving the dial ----
const ruler = ref<HTMLElement | null>(null)
const width = ref(0)
let resize: ResizeObserver | null = null
onMounted(() => {
  resize = new ResizeObserver(() => (width.value = ruler.value?.clientWidth ?? 0))
  if (ruler.value) resize.observe(ruler.value)
})
let frame = 0
function stopMotion() {
  cancelAnimationFrame(frame)
  frame = 0
}
onBeforeUnmount(() => {
  stopMotion()
  resize?.disconnect()
  window.clearTimeout(tuneTimer)
})
const clamp = (v: number) => Math.max(0, Math.min(dial.value.steps - 1, v))
/** Glides to a step, then tunes it. */
function glideTo(target: number, ms = 320) {
  stopMotion()
  const from = pos.value
  const t0 = performance.now()
  const run = (now: number) => {
    const k = Math.min(1, (now - t0) / ms)
    pos.value = from + (target - from) * (1 - (1 - k) ** 3)
    if (k < 1) frame = requestAnimationFrame(run)
    else {
      frame = 0
      pos.value = target
      settle()
    }
  }
  frame = requestAnimationFrame(run)
}
/** Where a resting dial lands: a whole step, pulled onto a station one step away. */
function rest() {
  let target = clamp(Math.round(pos.value))
  const near = dial.value.stops.find((s) => Math.abs(s.step - target) <= 1)
  if (near) target = near.step
  pickedAlt.value = 0
  glideTo(target, 180)
}

let drag: { x: number; pos: number; moved: boolean; lastX: number; lastT: number; v: number } | null = null
function down(e: PointerEvent) {
  if (e.button !== 0) return
  touched()
  stopMotion()
  window.clearTimeout(tuneTimer)
  ruler.value?.setPointerCapture(e.pointerId)
  drag = { x: e.clientX, pos: pos.value, moved: false, lastX: e.clientX, lastT: performance.now(), v: 0 }
}
function move(e: PointerEvent) {
  if (!drag) return
  const dx = e.clientX - drag.x
  if (Math.abs(dx) > 4) drag.moved = true
  pos.value = clamp(drag.pos - dx / dial.value.px)
  const now = performance.now()
  const dt = now - drag.lastT
  if (dt > 0) drag.v = 0.8 * (-(e.clientX - drag.lastX) / dial.value.px / dt) + 0.2 * drag.v // steps per ms
  drag.lastX = e.clientX
  drag.lastT = now
}
function up(e: PointerEvent) {
  if (!drag) return
  const d = drag
  drag = null
  if (!d.moved) {
    // a tap: to the place tapped
    const box = ruler.value!.getBoundingClientRect()
    glideTo(clamp(Math.round(pos.value + (e.clientX - box.left - box.width / 2) / dial.value.px)))
    return
  }
  // flung: slides on, slowing down
  let v = performance.now() - d.lastT > 80 ? 0 : d.v * 16 // steps per frame
  const run = () => {
    v *= 0.92
    pos.value = clamp(pos.value + v)
    if (Math.abs(v) > 0.05 && pos.value > 0 && pos.value < dial.value.steps - 1) frame = requestAnimationFrame(run)
    else {
      frame = 0
      rest()
    }
  }
  frame = requestAnimationFrame(run)
}
let wheelSum = 0
function wheel(e: WheelEvent) {
  e.preventDefault()
  stopScan()
  wheelSum += Math.abs(e.deltaX) > Math.abs(e.deltaY) ? e.deltaX : e.deltaY
  if (Math.abs(wheelSum) < 30) return
  const dir = wheelSum > 0 ? 1 : -1
  wheelSum = 0
  stopMotion()
  pickedAlt.value = 0
  pos.value = clamp(step.value + dir)
  settle()
}
function key(e: KeyboardEvent) {
  const big = dial.value.band === 'NET' ? 1 : 10
  const by: Record<string, number> = { ArrowRight: 1, ArrowUp: 1, ArrowLeft: -1, ArrowDown: -1, PageUp: big, PageDown: -big }
  let target: number | null = null
  if (e.key in by) target = clamp(step.value + by[e.key] * (e.shiftKey ? big : 1))
  else if (e.key === 'Home') target = 0
  else if (e.key === 'End') target = dial.value.steps - 1
  if (target === null) return
  e.preventDefault()
  touched()
  stopScan()
  stopMotion()
  pickedAlt.value = 0
  pos.value = target
  settle()
}
function seek(dir: 1 | -1) {
  const stop = nextStop(dial.value, step.value, dir)
  if (!stop) return
  pickedAlt.value = 0
  glideTo(stop.step, 520)
}

// ---- the dial drawn: ticks every step, longer every few, labelled ones; a dot at each station ----
const PAD = 24
const shift = computed(() => width.value / 2 - PAD - pos.value * dial.value.px)
const ticks = computed(() => {
  const d = dial.value
  return Array.from({ length: d.steps }, (_, i) => ({
    x: PAD + i * d.px,
    h: d.band === 'NET' || i % d.major === 0 ? 22 : i % d.mid === 0 ? 15 : 9,
    label: d.band === 'NET' || i % d.major === 0 ? tickLabel(d, i) : '',
  }))
})
const svgWidth = computed(() => PAD * 2 + (dial.value.steps - 1) * dial.value.px)

const isFavorite = computed(() => !!station.value && ui.radio.favorites.includes(station.value.id))
function toggleFavorite() {
  const st = station.value
  if (!st) return
  const f = ui.radio.favorites
  ui.radio = { ...ui.radio, favorites: isFavorite.value ? f.filter((x) => x !== st.id) : [...f, st.id] }
}
// iPhone and iPad: a web page can't change the volume (the device's buttons do)
const fixedVolume = /iPhone|iPad|iPod/.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1)
const unit = computed(() => (band.value === 'FM' ? 'FM' : band.value === 'AM' ? 'AM' : 'CH'))
const shownFreq = computed(() => dial.value.label(step.value))
const playingHere = computed(() => !!station.value && live.value?.id === station.value.id && player.playing)
const onAir = useOnAir(computed(() => station.value?.id))

async function share() {
  const st = station.value
  if (!st) return
  const text = [st.name, band.value === 'NET' ? '' : `${unit.value} ${shownFreq.value}`, onAir.value?.title ?? ''].filter(Boolean).join(' · ')
  try {
    if (navigator.share) await navigator.share({ title: st.name, text })
    else {
      await navigator.clipboard.writeText(text)
      ui.notify(t('radio.copied'))
    }
  } catch {
    /* closed */
  }
}

// ---- SCAN: the next station every seven seconds, until a tap ----
const SCAN_MS = 7000
const scanning = ref<0 | 1 | -1>(0)
let scanTimer = 0
function startScan(dir: 1 | -1) {
  scanning.value = dir
  const next = () => {
    seek(dir)
    scanTimer = window.setTimeout(next, SCAN_MS)
  }
  next()
}
function stopScan() {
  if (!scanning.value) return
  scanning.value = 0
  window.clearTimeout(scanTimer)
}
// ---- the hiss between stations (off unless turned on) ----
const noiseOn = computed(() => !!ui.radio.tunerNoise)
function toggleNoise() {
  ui.radio = { ...ui.radio, tunerNoise: !noiseOn.value }
  if (noiseOn.value) wakeNoise()
  else stopNoise()
}
function touched() {
  if (noiseOn.value) wakeNoise()
}
watch([pos, noiseOn, band], () => {
  if (!noiseOn.value || band.value === 'NET') return setNoise(0)
  const near = Math.min(...dial.value.stops.map((s) => Math.abs(s.step - pos.value)), 99)
  setNoise(near < 0.35 ? 0 : Math.min(1, (near - 0.35) / 1.2))
})
function hidden() {
  if (document.hidden) stopNoise()
}
onMounted(() => document.addEventListener('visibilitychange', hidden))
onBeforeUnmount(() => {
  document.removeEventListener('visibilitychange', hidden)
  stopNoise()
  window.clearTimeout(scanTimer)
})
</script>

<template>
  <div class="mx-auto flex w-full max-w-[720px] flex-col items-center gap-4 md:gap-5" @pointerdown.capture="stopScan">
    <!-- region, bands and the station's star -->
    <div class="grid w-full grid-cols-[1fr_auto_1fr] items-center gap-1">
      <label class="relative inline-flex items-center justify-self-start text-[15px] text-muted">
        <select v-model="region" :aria-label="t('common.region')" class="max-w-[9rem] appearance-none truncate bg-transparent pr-5 outline-none [field-sizing:content]">
          <option v-for="r in regions" :key="r" :value="r">{{ t(`radio.region_${r}`) }}</option>
        </select>
        <ChevronDown :size="15" :stroke-width="1.8" class="pointer-events-none absolute right-0" aria-hidden="true" />
      </label>
      <div v-if="bands.length > 1" class="flex rounded-full bg-surface p-0.5" role="tablist" :aria-label="t('radio.band')">
        <button
          v-for="b in bands"
          :key="b"
          type="button"
          role="tab"
          :aria-selected="band === b"
          class="h-7 min-w-11 rounded-full px-2.5 text-[13px] font-medium"
          :class="band === b ? 'bg-bg text-ink shadow-sm' : 'text-muted'"
          @click="pickBand(b)"
        >{{ b }}</button>
      </div>
      <span v-else />
      <div class="flex items-center justify-self-end">
        <button type="button" class="grid size-10 place-items-center rounded-full" :class="noiseOn ? 'text-accent' : 'text-muted'" :aria-pressed="noiseOn" :aria-label="t('radio.noise')" :title="t('radio.noise')" @click="toggleNoise">
          <AudioWaveform :size="21" :stroke-width="1.7" />
        </button>
        <button type="button" class="grid size-10 place-items-center rounded-full text-accent disabled:opacity-30" :disabled="!station" :aria-label="t('radio.share')" :title="t('radio.share')" @click="share">
          <Share2 :size="21" :stroke-width="1.7" />
        </button>
        <button
          type="button"
          class="grid size-10 place-items-center rounded-full text-accent disabled:opacity-30"
          :disabled="!station"
          :aria-label="isFavorite ? t('radio.unfavorite') : t('radio.favorite')"
          :aria-pressed="isFavorite"
          @click="toggleFavorite"
        >
          <Star :size="25" :stroke-width="1.6" :fill="isFavorite ? 'currentColor' : 'none'" />
        </button>
      </div>
    </div>

    <!-- the station: its image, the frequency, its name -->
    <div class="flex w-full flex-col items-center gap-1 text-center" aria-live="polite">
      <div class="mb-1 h-12 transition-opacity md:mb-2 md:h-16" :class="station ? 'opacity-100' : 'opacity-25'">
        <StationBadge v-if="station" :stn="station.stn" :logo="station.logo" class="h-12 text-[16px] md:h-16 md:text-[20px]" />
        <span v-else class="block h-12 w-[72px] rounded-[18%] bg-surface md:h-16 md:w-24" />
      </div>
      <p class="flex items-baseline gap-2 text-ink">
        <span class="text-[76px] font-extralight tabular-nums leading-none tracking-tight md:text-[112px]">{{ shownFreq }}</span>
        <span class="flex flex-col items-start">
          <span v-if="scanning" class="animate-pulse rounded bg-accent px-1.5 text-[11px] font-bold leading-[18px] text-white">SCAN</span>
          <span class="text-[24px] font-light md:text-[30px]">{{ unit }}</span>
        </span>
      </p>
      <p class="mt-1 min-h-[28px] max-w-full truncate text-[21px] font-medium md:text-[24px]">{{ station?.name ?? '—' }}</p>
      <!-- what it has on air now (the "radio title"), when its broadcaster says -->
      <p v-if="station && onAir" class="max-w-full truncate text-[16px] text-ink/80 md:text-[17px]">{{ onAirText(onAir) }}</p>
      <p class="min-h-[20px] truncate text-[14px] text-muted">
        <template v-if="station">CH {{ channel }} · {{ t(`radio.region_${region}`) }}</template>
        <template v-else>{{ t('radio.noStation') }}</template>
      </p>
      <!-- two stations on this frequency: the other one -->
      <button v-if="here.length > 1" type="button" class="mt-1 rounded-full bg-surface px-3 py-1 text-[13px] hover:bg-surface-2" @click="pickedAlt = (pickedAlt + 1) % here.length; settle()">
        {{ t('radio.otherHere', { name: here[(pickedAlt + 1) % here.length].name }) }}
      </button>
      <button type="button" class="mt-0.5 flex items-center gap-0.5 text-[15px] text-accent md:text-[16px]" @click="emit('list')">
        {{ t('radio.moreStations') }}<ChevronRight :size="17" :stroke-width="1.8" />
      </button>
    </div>

    <!-- the dial: slides under the needle -->
    <div
      ref="ruler"
      class="relative h-[96px] w-[calc(100%+40px)] cursor-grab touch-none select-none overflow-hidden border-y border-line bg-surface outline-none focus-visible:ring-2 focus-visible:ring-ink active:cursor-grabbing md:w-full md:rounded-2xl md:border"
      role="slider"
      tabindex="0"
      :aria-label="t('radio.dial')"
      :aria-valuemin="0"
      :aria-valuemax="dial.steps - 1"
      :aria-valuenow="step"
      :aria-valuetext="`${unit} ${shownFreq}${station ? ', ' + station.name : ''}`"
      @pointerdown="down"
      @pointermove="move"
      @pointerup="up"
      @pointercancel="up"
      @wheel="wheel"
      @keydown="key"
    >
      <svg :width="svgWidth" height="96" class="absolute left-0 top-0 text-muted" :style="{ transform: `translateX(${shift}px)` }" aria-hidden="true">
        <g v-for="(k, i) in ticks" :key="i">
          <line :x1="k.x" :x2="k.x" :y1="96 - 24" :y2="96 - 24 - k.h" stroke="currentColor" :stroke-width="k.label ? 1.4 : 1" :opacity="k.label ? 0.9 : 0.55" />
          <text v-if="k.label" :x="k.x" y="30" text-anchor="middle" font-size="15" fill="currentColor" class="tabular-nums">{{ k.label }}</text>
        </g>
        <circle v-for="s in dial.stops" :key="`s${s.step}`" :cx="PAD + s.step * dial.px" cy="84" r="3" class="fill-accent" />
      </svg>
      <!-- the needle -->
      <span class="pointer-events-none absolute inset-y-0 left-1/2 w-[3px] -translate-x-1/2 rounded-full bg-accent" />
    </div>

    <!-- seek, play -->
    <div class="flex w-full max-w-[360px] items-center justify-between px-4">
      <button v-long-press="() => startScan(-1)" type="button" class="grid size-14 select-none place-items-center rounded-full hover:bg-surface [-webkit-touch-callout:none]" :aria-label="t('radio.seekPrev')" :title="t('radio.seekPrevHelp')" @click="touched(); seek(-1)">
        <PlayerIcons name="rewind" :size="32" :stroke="1.5" />
      </button>
      <button type="button" class="grid size-16 place-items-center rounded-full hover:bg-surface disabled:opacity-30" :disabled="!station" :aria-label="playingHere ? t('player.pause') : t('player.play')" @click="toggle">
        <PlayerIcons :name="playingHere ? 'pause' : 'play'" :size="34" :stroke="1.6" />
      </button>
      <button v-long-press="() => startScan(1)" type="button" class="grid size-14 select-none place-items-center rounded-full hover:bg-surface [-webkit-touch-callout:none]" :aria-label="t('radio.seekNext')" :title="t('radio.seekNextHelp')" @click="touched(); seek(1)">
        <PlayerIcons name="forward" :size="32" :stroke="1.5" />
      </button>
    </div>
    <label v-if="!fixedVolume" class="flex w-full max-w-[420px] items-center gap-3 px-4 text-muted">
      <Volume1 :size="18" :stroke-width="1.7" aria-hidden="true" />
      <input v-model.number="player.volume" type="range" min="0" max="1" step="0.01" class="flex-1 accent-accent" :aria-label="t('radio.volume')" />
      <Volume2 :size="18" :stroke-width="1.7" aria-hidden="true" />
    </label>
  </div>
</template>
