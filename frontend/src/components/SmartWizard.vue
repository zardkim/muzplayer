<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { ChevronLeft, Search, X } from '@lucide/vue'
import { api, query } from '../api'
import { errorMessage } from '../i18n'
import { useAuth } from '../stores/auth'
import type { Playlist, SmartRules, Taste, TasteOut, Track } from '../types'
import BaseModal from './BaseModal.vue'
import ChoiceChip from './ChoiceChip.vue'

// The smart playlist wizard: a question at a time. The first ones are the person's taste (kept with
// their account, shared by every list made from it: users.taste), the last ones this list's own
// (share of familiar songs, a seed song, length, name, how long its picks stay). tasteOnly: just the
// taste (settings). Each step shows how many songs the answers let in (POST /smart/preview).
const props = defineProps<{ playlist?: Playlist; tasteOnly?: boolean }>()
const emit = defineEmits<{ close: []; saved: [playlist: Playlist | null]; advanced: [] }>()
const { t } = useI18n()
const auth = useAuth()

const DECADES = [1960, 1970, 1980, 1990, 2000, 2010, 2020]
const MIXES = ['familiar', 'balanced', 'new'] as const
const COUNTS = [50, 100, 200]
const HOURS = [1, 2, 3]
const RECENT = [0, 1, 7, 30]
const LONGEST = [null, 6, 8, 10]
const REFRESH = ['daily', 'weekly', 'open'] as const

function emptyTaste(): Taste {
  return { genres: [], artists: [], decades: [], exclude_genres: [], exclude_artists: [], exclude_tracks: [], skip_charts: false, skip_recent_days: 1, max_minutes: null }
}
const taste = ref<Taste>(emptyTaste())
const hadTaste = ref(false) // a taste was saved before: changing it changes the lists made from it
const rules = ref<SmartRules>(
  props.playlist?.rules
    ? { ...JSON.parse(JSON.stringify(props.playlist.rules)), profile: true }
    : { match: 'all', rules: [], sort: 'random', limit: 100, profile: true, mix: 'balanced', minutes: null, per_artist: 3, seed: null, refresh: 'daily' },
)
const name = ref(props.playlist?.name ?? '')
const artistNames = ref(new Map<number, string>())
const suggested = ref<{ genres: { name: string; count: number; mine: boolean }[]; artists: { id: number; name: string; mine: boolean }[] }>({ genres: [], artists: [] })
const ready = ref(false)
const busy = ref(false)
const error = ref('')

type Step = 'genres' | 'artists' | 'decades' | 'mix' | 'exclude' | 'length' | 'finish'
const steps = computed<Step[]>(() => {
  const all: Step[] = props.tasteOnly ? ['genres', 'artists', 'decades', 'exclude'] : ['genres', 'artists', 'decades', 'mix', 'exclude', 'length', 'finish']
  return suggested.value.genres.length ? all : all.filter((s) => s !== 'genres') // a library without genre tags
})
const at = ref(0)
const step = computed(() => steps.value[at.value])
const last = computed(() => at.value === steps.value.length - 1)

onMounted(async () => {
  try {
    const [mine, s, lists] = await Promise.all([
      api<TasteOut>('/taste'),
      api<typeof suggested.value>('/taste/suggest'),
      props.playlist || props.tasteOnly ? Promise.resolve({ items: [] as Playlist[] }) : api<{ items: Playlist[] }>('/playlists'),
    ])
    suggested.value = s
    for (const a of [...s.artists, ...mine.artists]) artistNames.value.set(a.id, a.name)
    if (mine.taste) {
      taste.value = mine.taste
      hadTaste.value = true
    } else {
      // first time: what they play and like most, picked already (changed freely)
      taste.value.genres = s.genres.filter((g) => g.mine).slice(0, 3).map((g) => g.name)
      taste.value.artists = s.artists.filter((a) => a.mine).slice(0, 5).map((a) => a.id)
    }
    if (!name.value) name.value = defaultName(lists.items.map((p) => p.name))
  } catch (e) {
    error.value = errorMessage(e)
  }
  ready.value = true
})

// "<id>의 스마트 재생목록", and a number after it when there is one by that name already
function defaultName(taken: string[]) {
  const base = t('smartWizard.defaultName', { name: auth.user?.username ?? '' })
  if (!taken.includes(base)) return base
  let n = 2
  while (taken.includes(`${base} ${n}`)) n++
  return `${base} ${n}`
}

function toggle<T>(list: T[], value: T) {
  const i = list.indexOf(value)
  if (i >= 0) list.splice(i, 1)
  else list.push(value)
}

// ---- artists: the suggested ones, and any found by name ----
const artistQ = ref('')
const found = ref<{ id: number; name: string }[]>([])
let findTimer = 0
watch(artistQ, (q) => {
  clearTimeout(findTimer)
  if (!q.trim()) return void (found.value = [])
  findTimer = window.setTimeout(async () => {
    const r = await api<{ items: { id: number; name: string }[] }>(`/artists${query({ q: q.trim(), limit: 12 })}`).catch(() => ({ items: [] }))
    for (const a of r.items) artistNames.value.set(a.id, a.name)
    found.value = r.items
  }, 300)
})
// the chips of a step: the ones chosen (wherever they came from), then the others offered
function artistChips(chosen: number[]) {
  const offered = (artistQ.value.trim() ? found.value : suggested.value.artists).map((a) => a.id)
  return [...new Set([...chosen, ...offered])]
}
const genreChips = computed(() => [...new Set([...taste.value.genres, ...suggested.value.genres.map((g) => g.name)])])
const excludeGenreChips = computed(() => [...new Set([...taste.value.exclude_genres, ...suggested.value.genres.map((g) => g.name)])])

// ---- a seed song: songs like it first ----
const seedQ = ref('')
const seedFound = ref<Track[]>([])
const seedTrack = ref<{ id: number; title: string; artist: string | null } | null>(null)
let seedTimer = 0
watch(seedQ, (q) => {
  clearTimeout(seedTimer)
  if (!q.trim()) return void (seedFound.value = [])
  seedTimer = window.setTimeout(async () => {
    seedFound.value = (await api<{ items: Track[] }>(`/tracks${query({ q: q.trim(), sort: 'relevance', limit: 6 })}`).catch(() => ({ items: [] }))).items
  }, 300)
})
function pickSeed(tr: Track | null) {
  rules.value.seed = tr?.id ?? null
  seedTrack.value = tr ? { id: tr.id, title: tr.title, artist: tr.artist } : null
  seedQ.value = ''
}

// ---- length: a number of songs or a time ----
const byTime = computed(() => !!rules.value.minutes)
function setCount(n: number) {
  rules.value.minutes = null
  rules.value.limit = n
}
function setHours(h: number) {
  rules.value.minutes = h * 60
  rules.value.limit = 500 // the time decides
}

// ---- how many songs the answers let in (the newest answer only) ----
interface Preview { matching: number; count: number; minutes: number; tracks: Track[]; seed: { id: number; title: string; artist: string | null } | null }
const preview = ref<Preview | null>(null)
let asked = 0
let previewTimer = 0
watch(
  [taste, rules, ready],
  () => {
    if (!ready.value) return
    clearTimeout(previewTimer)
    previewTimer = window.setTimeout(async () => {
      const mine = ++asked
      try {
        const r = await api<Preview>('/smart/preview', { method: 'POST', body: { rules: rules.value, taste: taste.value } })
        if (mine !== asked) return
        preview.value = r
        if (r.seed && !seedTrack.value) seedTrack.value = r.seed
      } catch {
        if (mine === asked) preview.value = null
      }
    }, 350)
  },
  { deep: true },
)

async function save() {
  busy.value = true
  error.value = ''
  try {
    await api('/taste', { method: 'PUT', body: taste.value })
    if (props.tasteOnly) return emit('saved', null)
    const body = { name: name.value.trim(), rules: rules.value }
    const p = props.playlist
      ? await api<Playlist>(`/playlists/${props.playlist.id}`, { method: 'PATCH', body })
      : await api<Playlist>('/playlists', { method: 'POST', body })
    emit('saved', p)
  } catch (e) {
    error.value = errorMessage(e)
  } finally {
    busy.value = false
  }
}
function next() {
  if (last.value) save()
  else at.value++
}
</script>

<template>
  <BaseModal :title="tasteOnly ? t('smartWizard.tasteTitle') : playlist ? t('smart.edit') : t('smart.new')" @close="emit('close')">
    <form v-if="ready" class="flex flex-col gap-4" @submit.prevent="next">
      <!-- where in the questions: one bar per step -->
      <div class="flex gap-1" aria-hidden="true">
        <span v-for="(s, i) in steps" :key="s" class="h-1 flex-1 rounded-full" :class="i <= at ? 'bg-ink' : 'bg-line'" />
      </div>
      <h3 class="text-[19px] font-bold">{{ t(`smartWizard.q.${step}`) }}</h3>
      <p class="-mt-2 text-[14px] font-light text-muted">{{ t(`smartWizard.help.${step}`) }}</p>
      <p v-if="hadTaste && at === 0 && !tasteOnly" class="rounded-xl bg-surface px-3.5 py-2.5 text-[13px] text-muted">{{ t('smartWizard.shared') }}</p>

      <div v-if="step === 'genres'" class="flex flex-wrap gap-2">
        <ChoiceChip v-for="g in genreChips" :key="g" small :active="taste.genres.includes(g)" @click="toggle(taste.genres, g)">{{ g }}</ChoiceChip>
      </div>

      <template v-else-if="step === 'artists' || step === 'exclude'">
        <template v-if="step === 'exclude'">
          <template v-if="suggested.genres.length">
            <h4 class="text-[14px] font-semibold">{{ t('smartWizard.excludeGenres') }}</h4>
            <div class="flex flex-wrap gap-2">
              <ChoiceChip v-for="g in excludeGenreChips" :key="g" small :active="taste.exclude_genres.includes(g)" @click="toggle(taste.exclude_genres, g)">{{ g }}</ChoiceChip>
            </div>
          </template>
          <h4 class="text-[14px] font-semibold">{{ t('smartWizard.excludeArtists') }}</h4>
        </template>
        <label class="flex h-10 items-center gap-2 rounded-full bg-surface px-3.5">
          <Search :size="16" class="flex-none text-muted" />
          <input v-model="artistQ" type="search" class="min-w-0 flex-1 bg-transparent text-[15px] outline-none" :placeholder="t('smartWizard.findArtist')" :aria-label="t('smartWizard.findArtist')" />
        </label>
        <div class="flex flex-wrap gap-2">
          <template v-for="id in artistChips(step === 'artists' ? taste.artists : taste.exclude_artists)" :key="id">
            <ChoiceChip
              small
              :active="(step === 'artists' ? taste.artists : taste.exclude_artists).includes(id)"
              @click="toggle(step === 'artists' ? taste.artists : taste.exclude_artists, id)"
            >{{ artistNames.get(id) ?? `#${id}` }}</ChoiceChip>
          </template>
        </div>
        <template v-if="step === 'exclude'">
          <label class="flex items-center gap-2.5 text-[15px]">
            <input v-model="taste.skip_charts" type="checkbox" class="size-4 accent-ink" />{{ t('smartWizard.skipCharts') }}
          </label>
          <label class="flex flex-wrap items-center gap-2.5 text-[15px]">
            {{ t('smartWizard.skipRecent') }}
            <select v-model.number="taste.skip_recent_days" class="pill-select">
              <option v-for="d in RECENT" :key="d" :value="d">{{ d ? t('smartWizard.days', { n: d }) : t('smartWizard.none') }}</option>
            </select>
          </label>
          <label class="flex flex-wrap items-center gap-2.5 text-[15px]">
            {{ t('smartWizard.longest') }}
            <select v-model="taste.max_minutes" class="pill-select">
              <option v-for="m in LONGEST" :key="m ?? 0" :value="m">{{ m ? t('smartWizard.overMinutes', { n: m }) : t('smartWizard.none') }}</option>
            </select>
          </label>
          <p v-if="taste.exclude_tracks.length" class="text-[13px] text-muted">{{ t('smartWizard.excludedSongs', { n: taste.exclude_tracks.length }) }}</p>
        </template>
      </template>

      <div v-else-if="step === 'decades'" class="flex flex-wrap gap-2">
        <ChoiceChip small :active="!taste.decades.length" @click="taste.decades = []">{{ t('smartWizard.anyDecade') }}</ChoiceChip>
        <ChoiceChip v-for="d in DECADES" :key="d" small :active="taste.decades.includes(d)" @click="toggle(taste.decades, d)">{{ t('smartWizard.decade', { n: d }) }}</ChoiceChip>
      </div>

      <template v-else-if="step === 'mix'">
        <div class="flex flex-col gap-2" role="radiogroup">
          <button
            v-for="m in MIXES"
            :key="m"
            type="button"
            role="radio"
            :aria-checked="rules.mix === m"
            class="flex flex-col items-start rounded-2xl border px-4 py-3 text-left"
            :class="rules.mix === m ? 'border-ink bg-surface' : 'border-line'"
            @click="rules.mix = m"
          >
            <span class="text-[15px] font-semibold">{{ t(`smartWizard.mixes.${m}`) }}</span>
            <span class="text-[13px] font-light text-muted">{{ t(`smartWizard.mixHelp.${m}`) }}</span>
          </button>
        </div>
        <label class="flex items-center gap-2.5 text-[15px]">
          <input type="checkbox" class="size-4 accent-ink" :checked="!!rules.per_artist" @change="rules.per_artist = ($event.target as HTMLInputElement).checked ? 3 : null" />
          {{ t('smartWizard.spread') }}
        </label>
        <h4 class="text-[14px] font-semibold">{{ t('smartWizard.seed') }}</h4>
        <div v-if="seedTrack" class="flex items-center gap-2 rounded-xl bg-surface px-3.5 py-2.5 text-[14px]">
          <span class="min-w-0 flex-1 truncate">{{ seedTrack.title }}<span v-if="seedTrack.artist" class="text-muted"> · {{ seedTrack.artist }}</span></span>
          <button type="button" class="grid size-8 place-items-center text-muted" :aria-label="t('smartWizard.seedRemove')" @click="pickSeed(null)"><X :size="16" /></button>
        </div>
        <template v-else>
          <label class="flex h-10 items-center gap-2 rounded-full bg-surface px-3.5">
            <Search :size="16" class="flex-none text-muted" />
            <input v-model="seedQ" type="search" class="min-w-0 flex-1 bg-transparent text-[15px] outline-none" :placeholder="t('smartWizard.findSong')" :aria-label="t('smartWizard.findSong')" />
          </label>
          <ul v-if="seedFound.length" class="flex flex-col">
            <li v-for="tr in seedFound" :key="tr.id">
              <button type="button" class="w-full truncate rounded-lg px-3 py-2 text-left text-[14px] hover:bg-surface" @click="pickSeed(tr)">{{ tr.title }}<span class="text-muted"> · {{ tr.artist }}</span></button>
            </li>
          </ul>
        </template>
      </template>

      <template v-else-if="step === 'length'">
        <div class="flex flex-wrap gap-2">
          <ChoiceChip v-for="n in COUNTS" :key="n" small :active="!byTime && rules.limit === n" @click="setCount(n)">{{ t('common.tracks', n) }}</ChoiceChip>
          <ChoiceChip v-for="h in HOURS" :key="h" small :active="rules.minutes === h * 60" @click="setHours(h)">{{ t('smartWizard.hours', { n: h }) }}</ChoiceChip>
        </div>
      </template>

      <template v-else-if="step === 'finish'">
        <label class="flex flex-col gap-1.5 text-[13px] text-muted">
          {{ t('playlists.name') }}
          <input v-model="name" required maxlength="200" class="field h-12 px-4" />
        </label>
        <div class="flex flex-col gap-1.5">
          <span class="text-[13px] text-muted">{{ t('smartWizard.refresh') }}</span>
          <div class="flex flex-wrap gap-2">
            <ChoiceChip v-for="r in REFRESH" :key="r" small :active="(rules.refresh ?? 'open') === r" @click="rules.refresh = r">{{ t(`smartWizard.refreshes.${r}`) }}</ChoiceChip>
          </div>
        </div>
        <ol v-if="preview?.tracks.length" class="flex flex-col gap-1 rounded-2xl border border-line p-3 text-[14px]">
          <li v-for="tr in preview.tracks" :key="tr.id" class="truncate">{{ tr.title }}<span class="text-muted"> · {{ tr.artist }}</span></li>
          <li v-if="preview.count > preview.tracks.length" class="text-muted">…</li>
        </ol>
        <button type="button" class="self-start text-[13px] text-muted underline" @click="emit('advanced')">{{ t('smartWizard.advanced') }}</button>
      </template>

      <!-- what the answers so far let in -->
      <p class="text-[14px]" :class="preview && !preview.matching ? 'text-danger' : 'text-muted'" aria-live="polite">
        <template v-if="preview">
          {{ preview.matching ? t('smartWizard.matching', { n: preview.matching }) : t('smartWizard.noMatch') }}
          <template v-if="!tasteOnly && preview.matching && (step === 'length' || step === 'finish')"> · {{ t('smartWizard.result', { n: preview.count, m: preview.minutes }) }}</template>
        </template>
        <template v-else>&nbsp;</template>
      </p>

      <p v-if="error" class="text-[14px] text-danger" role="alert">{{ error }}</p>
      <div class="flex gap-2">
        <button v-if="at > 0" type="button" class="flex h-12 items-center gap-1 rounded-full border border-line-strong px-4" @click="at--">
          <ChevronLeft :size="18" />{{ t('smartWizard.back') }}
        </button>
        <button type="submit" class="h-12 flex-1 rounded-full bg-ink text-on-ink disabled:opacity-40" :disabled="busy || (step === 'finish' && !name.trim())">
          {{ last ? t('common.save') : t('smartWizard.next') }}
        </button>
      </div>
    </form>
    <p v-else-if="error" class="text-[14px] text-danger" role="alert">{{ error }}</p>
  </BaseModal>
</template>
