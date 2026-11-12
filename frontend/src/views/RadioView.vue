<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { Eye, EyeOff, MapPin, Pencil, Plus, Square, Star, Trash2 } from '@lucide/vue'
import { api } from '../api'
import { errorMessage } from '../i18n'
import { forgetStations, loadStations } from '../radio'
import { usePlayer } from '../stores/player'
import { useUi } from '../stores/ui'
import type { RadioStation, ViewMode } from '../types'
import BaseModal from '../components/BaseModal.vue'
import PageHeader from '../components/PageHeader.vue'
import PlayerIcons from '../components/PlayerIcons.vue'
import RadioTuner from '../components/RadioTuner.vue'
import SectionTitle from '../components/SectionTitle.vue'
import SelectPill from '../components/SelectPill.vue'
import StationBadge from '../components/StationBadge.vue'
import ViewToggle from '../components/ViewToggle.vue'

// Korean radio, live (backend radio.py relays each station). Stations by region, as a list or as
// cards with the logo large; the region and the view picked last are remembered. Anyone can add
// stations by their address (their own, "your stations") and hide the ones they never listen to
// (editing shows them again, each with a way back); both are kept with the account.
const { t } = useI18n()
const player = usePlayer()
const ui = useUi()
const regions = ref<string[]>([])
const stations = ref<RadioStation[]>([])
const error = ref('')
const region = computed({
  get: () => ui.views.radio || 'seoul',
  set: (v: string) => (ui.views = { ...ui.views, radio: v }),
})
const view = computed(() => ((ui.views.radioView as ViewMode) === 'cover' ? 'cover' : 'list'))
// the stations as a list, or on a tuner's dial by frequency (RadioTuner); the one picked is remembered
const mode = computed({
  get: () => (ui.views.radioMode === 'tuner' ? 'tuner' : 'list'),
  set: (v: 'list' | 'tuner') => (ui.views = { ...ui.views, radioMode: v }),
})
const editing = ref(false)
const hidden = computed(() => new Set(ui.radio.hidden ?? []))
const isHidden = (s: RadioStation) => hidden.value.has(s.id)
const visible = (s: RadioStation) => editing.value || !isHidden(s)
const shown = computed(() => stations.value.filter((s) => s.regions.includes(region.value) && visible(s)))
const custom = computed(() => stations.value.filter((s) => s.custom && visible(s)))
// one's own station that is a listed one again (by its address, or by its name): said so, it can go
function listedTwin(s: RadioStation): RadioStation | null {
  return stations.value.find((x) => !x.custom && (x.id === s.same_as || x.name.replace(/\s/g, '') === s.name.replace(/\s/g, ''))) ?? null
}
const hiddenCount = computed(() => stations.value.filter(isHidden).length)
function toggleHidden(s: RadioStation) {
  const h = ui.radio.hidden ?? []
  ui.radio = { ...ui.radio, hidden: isHidden(s) ? h.filter((x) => x !== s.id) : [...h, s.id] }
}
const live = computed(() => (player.mode === 'live' ? player.station : null))

async function load() {
  try {
    const r = await loadStations()
    regions.value = r.regions
    stations.value = r.stations
  } catch (e) {
    error.value = errorMessage(e)
  }
}
onMounted(load)

// a station of one's own, by its address (the server checks that it plays)
const adding = ref(false)
const form = ref({ name: '', url: '' })
const formError = ref('')
const saving = ref(false)
async function addStation() {
  saving.value = true
  formError.value = ''
  try {
    const st = await api<RadioStation>('/radio/custom', { method: 'POST', body: form.value })
    forgetStations()
    await load()
    adding.value = false
    form.value = { name: '', url: '' }
    ui.notify(t('radio.added'))
    player.playStation(st)
  } catch (e) {
    formError.value = errorMessage(e)
  } finally {
    saving.value = false
  }
}
async function removeStation(s: RadioStation) {
  if (!confirm(`${t('radio.remove')}: ${s.name}`)) return
  try {
    await api(`/radio/custom/${s.id.slice(1)}`, { method: 'DELETE' })
    if (live.value?.id === s.id) player.stopStation()
    ui.radio = {
      ...ui.radio,
      recent: ui.radio.recent.filter((x) => x !== s.id),
      favorites: ui.radio.favorites.filter((x) => x !== s.id),
      hidden: (ui.radio.hidden ?? []).filter((x) => x !== s.id),
    }
    forgetStations()
    await load()
    ui.notify(t('radio.removed'))
  } catch (e) {
    ui.notify(errorMessage(e), true)
  }
}
const field = 'h-12 rounded-full bg-surface px-4 text-base text-ink outline-none focus:ring-2 focus:ring-ink'

// starred stations and the ones listened to lately (any region), kept with the account
const byId = computed(() => new Map(stations.value.map((s) => [s.id, s])))
const pick = (ids: string[]) => ids.map((id) => byId.value.get(id)).filter((s): s is RadioStation => !!s && !isHidden(s))
const favorites = computed(() => pick(ui.radio.favorites))
const recent = computed(() => pick(ui.radio.recent))
const isFavorite = (s: RadioStation) => ui.radio.favorites.includes(s.id)
function toggleFavorite(s: RadioStation) {
  const f = ui.radio.favorites
  ui.radio = { ...ui.radio, favorites: isFavorite(s) ? f.filter((x) => x !== s.id) : [...f, s.id] }
}

function tune(s: RadioStation) {
  if (live.value?.id === s.id) player.toggle()
  else player.playStation(s)
}
</script>

<template>
  <div class="flex flex-col gap-6">
    <PageHeader :title="t('radio.title')" :sub="stations.length ? t('radio.count', { n: shown.length }) : ''">
      <template #actions>
        <button type="button" class="grid size-10 place-items-center rounded-full hover:bg-surface" :aria-label="t('radio.add')" :title="t('radio.add')" @click="adding = true">
          <Plus :size="22" :stroke-width="1.7" />
        </button>
        <button
          v-if="mode === 'list'"
          type="button"
          class="flex h-10 items-center gap-1.5 rounded-full px-3 text-[15px]"
          :class="editing ? 'bg-ink font-medium text-on-ink' : 'hover:bg-surface'"
          :aria-pressed="editing"
          :aria-label="t('radio.edit')"
          :title="t('radio.edit')"
          @click="editing = !editing"
        >
          <template v-if="editing">{{ t('radio.editDone') }}</template>
          <Pencil v-else :size="19" :stroke-width="1.7" />
        </button>
      </template>
    </PageHeader>
    <div class="-mt-2 flex self-start rounded-full bg-surface p-1" role="tablist" :aria-label="t('radio.mode')">
      <button
        v-for="m in (['list', 'tuner'] as const)"
        :key="m"
        type="button"
        role="tab"
        :aria-selected="mode === m"
        class="h-8 rounded-full px-4 text-[14px] font-medium"
        :class="mode === m ? 'bg-bg text-ink shadow-sm' : 'text-muted'"
        @click="mode = m"
      >{{ t(`radio.mode_${m}`) }}</button>
    </div>
    <RadioTuner v-if="mode === 'tuner' && stations.length" v-model:region="region" :stations="stations.filter((s) => !isHidden(s))" :regions="regions" @list="mode = 'list'" />
    <template v-if="mode === 'list'">
    <p v-if="editing && hiddenCount" class="-mt-3 text-[14px] text-muted">{{ t('radio.hiddenCount', { n: hiddenCount }) }}</p>

    <!-- what is on now -->
    <div v-if="live" class="flex items-center gap-3.5 rounded-2xl bg-surface p-3.5">
      <button type="button" class="flex min-w-0 flex-1 items-center gap-3.5 text-left" :aria-label="t('player.open')" @click="ui.playerOpen = true">
      <StationBadge :stn="live.stn" :logo="live.logo" class="size-12 text-[15px]" />
      <span class="flex min-w-0 flex-1 flex-col">
        <span class="flex items-center gap-2"><span class="rounded bg-danger px-1.5 text-[11px] font-bold leading-[18px] text-white">LIVE</span><span class="truncate text-[17px] font-medium">{{ live.name }}</span></span>
        <span class="text-[13px] font-light text-muted">{{ player.playing ? t('radio.onAir') : t('radio.paused') }}</span>
      </span>
      </button>
      <button type="button" class="grid size-11 place-items-center rounded-full bg-ink text-on-ink" :aria-label="player.playing ? t('player.pause') : t('player.play')" @click="player.toggle()">
        <PlayerIcons :name="player.playing ? 'pause' : 'play'" :size="20" :stroke="1.8" />
      </button>
      <button type="button" class="grid size-11 place-items-center rounded-full border border-line-strong" :aria-label="t('radio.stop')" :title="t('radio.stop')" @click="player.stopStation()">
        <Square :size="16" :stroke-width="2" />
      </button>
    </div>

    <!-- starred and lately listened, from any region -->
    <section v-if="favorites.length" class="flex flex-col gap-3">
      <SectionTitle :title="t('radio.favorites')" />
      <ul class="-mr-5 flex gap-3 overflow-x-auto pb-1 pr-5 [scrollbar-width:none] md:mr-0 md:pr-0">
        <li v-for="s in favorites" :key="s.id" class="w-[92px] flex-none">
          <button type="button" class="flex w-full flex-col items-center gap-1.5 text-center" :aria-pressed="live?.id === s.id" @click="tune(s)">
            <span class="relative block w-full rounded-2xl" :class="live?.id === s.id ? 'ring-2 ring-accent ring-offset-2 ring-offset-bg' : ''">
              <StationBadge :stn="s.stn" :logo="s.logo" fill class="text-[18px]" />
              <span v-if="live?.id === s.id" class="absolute bottom-1.5 right-1.5 grid size-7 place-items-center rounded-full bg-ink text-on-ink shadow">
                <PlayerIcons :name="player.playing ? 'pause' : 'play'" :size="13" :stroke="1.8" />
              </span>
            </span>
            <span class="line-clamp-2 w-full text-[13px] leading-tight" :class="live?.id === s.id ? 'font-medium text-accent' : ''">{{ s.name }}</span>
          </button>
        </li>
      </ul>
    </section>
    <section v-if="recent.length" class="flex flex-col gap-3">
      <SectionTitle :title="t('radio.recent')" />
      <ul class="-mr-5 flex gap-3 overflow-x-auto pb-1 pr-5 [scrollbar-width:none] md:mr-0 md:pr-0">
        <li v-for="s in recent" :key="s.id" class="w-[92px] flex-none">
          <button type="button" class="flex w-full flex-col items-center gap-1.5 text-center" :aria-pressed="live?.id === s.id" @click="tune(s)">
            <span class="relative block w-full rounded-2xl" :class="live?.id === s.id ? 'ring-2 ring-accent ring-offset-2 ring-offset-bg' : ''">
              <StationBadge :stn="s.stn" :logo="s.logo" fill class="text-[18px]" />
              <span v-if="live?.id === s.id" class="absolute bottom-1.5 right-1.5 grid size-7 place-items-center rounded-full bg-ink text-on-ink shadow">
                <PlayerIcons :name="player.playing ? 'pause' : 'play'" :size="13" :stroke="1.8" />
              </span>
            </span>
            <span class="line-clamp-2 w-full text-[13px] leading-tight" :class="live?.id === s.id ? 'font-medium text-accent' : ''">{{ s.name }}</span>
          </button>
        </li>
      </ul>
    </section>

    <!-- the ones this person added by address -->
    <section v-if="custom.length" class="flex flex-col gap-3">
      <SectionTitle :title="t('radio.custom')" />
      <ul class="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
        <li v-for="s in custom" :key="s.id" class="flex items-center gap-1" :class="isHidden(s) ? 'opacity-50' : ''">
          <button
            type="button"
            class="flex min-w-0 flex-1 items-center gap-3.5 rounded-2xl p-2.5 text-left transition-colors"
            :class="live?.id === s.id ? 'bg-accent-soft' : 'hover:bg-surface'"
            :aria-pressed="live?.id === s.id"
            @click="tune(s)"
          >
            <StationBadge :stn="s.stn" :logo="s.logo" class="size-11 text-[13px]" />
            <span class="flex min-w-0 flex-1 flex-col">
              <span class="truncate text-[16px]" :class="live?.id === s.id ? 'font-medium text-accent' : ''">{{ s.name }}</span>
              <span v-if="listedTwin(s)" class="truncate text-[12px] text-accent">{{ t('radio.sameAs', { name: listedTwin(s)!.name }) }}</span>
              <span v-else class="truncate text-[12px] font-light text-muted">{{ s.url }}</span>
            </span>
            <PlayerIcons v-if="live?.id === s.id" :name="player.playing ? 'pause' : 'play'" :size="18" :stroke="1.8" class="mr-1.5 flex-none text-accent" />
          </button>
          <button v-if="editing" type="button" class="grid size-10 flex-none place-items-center rounded-full text-danger" :aria-label="`${t('radio.remove')}: ${s.name}`" :title="t('radio.remove')" @click="removeStation(s)">
            <Trash2 :size="18" :stroke-width="1.7" />
          </button>
          <button v-else type="button" class="grid size-10 flex-none place-items-center rounded-full" :class="isFavorite(s) ? 'text-accent' : 'text-muted hover:text-ink'" :aria-label="`${isFavorite(s) ? t('radio.unfavorite') : t('radio.favorite')}: ${s.name}`" :aria-pressed="isFavorite(s)" @click="toggleFavorite(s)">
            <Star :size="19" :stroke-width="1.7" :fill="isFavorite(s) ? 'currentColor' : 'none'" />
          </button>
        </li>
      </ul>
    </section>

    <div class="flex items-center justify-between gap-3">
      <SelectPill v-model="region" :label="t('common.region')" :icon="MapPin" :options="regions.map((r) => ({ value: r, label: t(`radio.region_${r}`) }))" />
      <ViewToggle page="radioView" fallback="list" :only="['list', 'cover']" />
    </div>

    <p v-if="error" class="font-light text-muted">{{ error }}</p>
    <ul v-if="view === 'cover'" class="grid grid-cols-2 gap-x-3 gap-y-4 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
      <li v-for="s in shown" :key="s.id" class="relative" :class="isHidden(s) ? 'opacity-50' : ''">
        <button type="button" class="group flex w-full flex-col gap-2 text-left" :aria-pressed="live?.id === s.id" @click="tune(s)">
          <span class="relative block w-full rounded-2xl transition-shadow" :class="live?.id === s.id ? 'ring-2 ring-accent ring-offset-2 ring-offset-bg' : ''">
            <StationBadge :stn="s.stn" :logo="s.logo" fill class="text-[30px] transition-transform group-active:scale-[0.97]" />
            <span v-if="live?.id === s.id" class="absolute bottom-2 right-2 grid size-9 place-items-center rounded-full bg-ink text-on-ink shadow">
              <PlayerIcons :name="player.playing ? 'pause' : 'play'" :size="16" :stroke="1.8" />
            </span>
          </span>
          <span class="truncate px-0.5 pr-8 text-[15px]" :class="live?.id === s.id ? 'font-medium text-accent' : ''">{{ s.name }}</span>
        </button>
        <button v-if="editing" type="button" class="absolute bottom-0 right-0 grid size-8 place-items-center rounded-full text-muted hover:text-ink" :aria-label="`${isHidden(s) ? t('radio.unhide') : t('radio.hide')}: ${s.name}`" :title="isHidden(s) ? t('radio.unhide') : t('radio.hide')" @click="toggleHidden(s)">
          <Eye v-if="isHidden(s)" :size="18" :stroke-width="1.7" /><EyeOff v-else :size="18" :stroke-width="1.7" />
        </button>
        <button v-else type="button" class="absolute bottom-0 right-0 grid size-8 place-items-center rounded-full" :class="isFavorite(s) ? 'text-accent' : 'text-muted hover:text-ink'" :aria-label="`${isFavorite(s) ? t('radio.unfavorite') : t('radio.favorite')}: ${s.name}`" :aria-pressed="isFavorite(s)" @click="toggleFavorite(s)">
          <Star :size="18" :stroke-width="1.7" :fill="isFavorite(s) ? 'currentColor' : 'none'" />
        </button>
      </li>
    </ul>
    <ul v-else class="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
      <li v-for="s in shown" :key="s.id" class="flex items-center gap-1" :class="isHidden(s) ? 'opacity-50' : ''">
        <button
          type="button"
          class="flex min-w-0 flex-1 items-center gap-3.5 rounded-2xl p-2.5 text-left transition-colors"
          :class="live?.id === s.id ? 'bg-accent-soft' : 'hover:bg-surface'"
          :aria-pressed="live?.id === s.id"
          @click="tune(s)"
        >
          <StationBadge :stn="s.stn" :logo="s.logo" class="size-11 text-[13px]" />
          <span class="min-w-0 flex-1 truncate text-[16px]" :class="live?.id === s.id ? 'font-medium text-accent' : ''">{{ s.name }}</span>
          <PlayerIcons v-if="live?.id === s.id" :name="player.playing ? 'pause' : 'play'" :size="18" :stroke="1.8" class="mr-1.5 flex-none text-accent" />
        </button>
        <button v-if="editing" type="button" class="grid size-10 flex-none place-items-center rounded-full text-muted hover:text-ink" :aria-label="`${isHidden(s) ? t('radio.unhide') : t('radio.hide')}: ${s.name}`" :title="isHidden(s) ? t('radio.unhide') : t('radio.hide')" @click="toggleHidden(s)">
          <Eye v-if="isHidden(s)" :size="19" :stroke-width="1.7" /><EyeOff v-else :size="19" :stroke-width="1.7" />
        </button>
        <button v-else type="button" class="grid size-10 flex-none place-items-center rounded-full" :class="isFavorite(s) ? 'text-accent' : 'text-muted hover:text-ink'" :aria-label="`${isFavorite(s) ? t('radio.unfavorite') : t('radio.favorite')}: ${s.name}`" :aria-pressed="isFavorite(s)" @click="toggleFavorite(s)">
          <Star :size="19" :stroke-width="1.7" :fill="isFavorite(s) ? 'currentColor' : 'none'" />
        </button>
      </li>
    </ul>
    </template>
    <p class="text-[12px] font-light text-subtle">{{ t('radio.source') }}</p>
    <BaseModal v-if="adding" :title="t('radio.addTitle')" @close="adding = false">
      <form class="flex flex-col gap-3.5" @submit.prevent="addStation">
        <label class="flex flex-col gap-1.5 text-[13px] text-muted">{{ t('radio.addName') }}<input v-model="form.name" required maxlength="100" :class="field" /></label>
        <label class="flex flex-col gap-1.5 text-[13px] text-muted">{{ t('radio.addUrl') }}<input v-model="form.url" type="url" required maxlength="2000" inputmode="url" autocapitalize="none" placeholder="https://" :class="field" /></label>
        <p class="text-[13px] font-light leading-relaxed text-muted">{{ t('radio.addHelp') }}</p>
        <p v-if="formError" role="alert" class="text-[13px] text-danger">{{ formError }}</p>
        <button type="submit" class="mt-1 h-12 rounded-full bg-ink text-on-ink disabled:opacity-50" :disabled="saving">{{ saving ? t('common.loading') : t('radio.addSave') }}</button>
      </form>
    </BaseModal>
  </div>
</template>
