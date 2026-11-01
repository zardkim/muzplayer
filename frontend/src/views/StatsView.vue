<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ChevronLeft } from '@lucide/vue'
import { api } from '../api'
import { errorMessage } from '../i18n'
import PageHeader from '../components/PageHeader.vue'

// Admin → statistics (backend stats.py): the library, the people, what was played in the last
// 30 days, and the disk this app uses. Headline numbers as tiles; one-series bars in the accent
// colour, each value shown on hover/focus and as text.
interface Stats {
  days: number
  library: {
    tracks: number; hours: number; bytes: number; albums: number; artists: number; genres: number; books: number
    missing: number; damaged: number; no_genre: number; with_notes: number; fetched_lyrics: number
    formats: { format: string; tracks: number; bytes: number }[]
    quality: { hires: number; lossless: number; lossy: number }
  }
  users: { total: number; active: number; admins: number; pending: number; seen_week: number; playlists: number }
  plays: {
    days: { day: string; plays: number }[]; last_days: number; hours: number; all_time: number
    top_tracks: { id: number; title: string; artist: string; plays: number }[]
    top_artists: { id: number; name: string; plays: number }[]
    per_user: { id: number; name: string; plays: number; hours: number }[]
  }
  storage: { database: number; covers: number; transcode: number }
}
const { t, locale } = useI18n()
const s = ref<Stats | null>(null)
const error = ref('')
onMounted(async () => {
  try {
    s.value = await api<Stats>('/admin/stats')
  } catch (e) {
    error.value = errorMessage(e)
  }
})

const num = (n: number) => n.toLocaleString(locale.value)
function size(bytes: number) {
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let v = bytes
  let i = 0
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024
    i++
  }
  return `${v >= 100 || i === 0 ? Math.round(v) : v.toFixed(1)} ${units[i]}`
}
const dayLabel = (iso: string) => new Date(`${iso}T00:00:00`).toLocaleDateString(locale.value, { month: 'numeric', day: 'numeric' })

const tiles = computed(() => {
  const x = s.value
  if (!x) return []
  return [
    { label: t('stats.tracks'), value: num(x.library.tracks), sub: t('stats.hours', { n: num(x.library.hours) }) },
    { label: t('stats.albums'), value: num(x.library.albums), sub: t('stats.artistsGenres', { a: num(x.library.artists), g: num(x.library.genres) }) },
    { label: t('stats.size'), value: size(x.library.bytes), sub: x.library.books ? t('stats.books', { n: num(x.library.books) }) : '' },
    { label: t('stats.playsDays', { n: x.days }), value: num(x.plays.last_days), sub: t('stats.hours', { n: num(x.plays.hours) }) },
    { label: t('stats.playsAll'), value: num(x.plays.all_time), sub: '' },
    { label: t('stats.users'), value: num(x.users.active), sub: t('stats.usersSub', { week: x.users.seen_week, pending: x.users.pending }) },
  ]
})
// the daily bars: scaled to the busiest day
const peak = computed(() => Math.max(1, ...(s.value?.plays.days.map((d) => d.plays) ?? [1])))
const hover = ref<number | null>(null)
const maxOf = (list: { plays?: number; tracks?: number }[], key: 'plays' | 'tracks') => Math.max(1, ...list.map((x) => x[key] ?? 0))
const quality = computed(() => {
  const q = s.value?.library.quality
  if (!q) return []
  const total = Math.max(1, q.hires + q.lossless + q.lossy)
  return (['hires', 'lossless', 'lossy'] as const).map((k) => ({ key: k, n: q[k], pct: Math.round((q[k] / total) * 100) }))
})
const checks = computed(() => {
  const l = s.value?.library
  if (!l) return []
  return [
    { label: t('stats.missing'), n: l.missing },
    { label: t('stats.damaged'), n: l.damaged },
    { label: t('stats.noGenre'), n: l.no_genre },
    { label: t('stats.withNotes'), n: l.with_notes },
    { label: t('stats.fetchedLyrics'), n: l.fetched_lyrics },
    { label: t('stats.playlists'), n: s.value!.users.playlists },
  ]
})
</script>

<template>
  <div class="flex flex-col gap-8">
    <RouterLink to="/admin" class="-mb-4 flex items-center gap-1 self-start text-[14px] text-muted hover:text-ink"><ChevronLeft :size="16" />{{ t('admin.title') }}</RouterLink>
    <PageHeader :title="t('stats.title')" />
    <p v-if="error" class="font-light text-muted">{{ error }}</p>
    <p v-else-if="!s" class="font-light text-muted">{{ t('common.loading') }}</p>
    <template v-else>
      <!-- headline numbers -->
      <div class="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <div v-for="x in tiles" :key="x.label" class="flex flex-col gap-1 rounded-2xl bg-surface px-4 py-3.5">
          <span class="text-[13px] text-muted">{{ x.label }}</span>
          <span class="font-display text-[26px] font-bold leading-tight">{{ x.value }}</span>
          <span class="truncate text-[12px] text-muted">{{ x.sub }}</span>
        </div>
      </div>

      <!-- plays per day -->
      <section class="flex flex-col gap-3 rounded-2xl border border-line p-5">
        <div class="flex items-baseline justify-between gap-3">
          <h2 class="text-lg font-bold">{{ t('stats.daily', { n: s.days }) }}</h2>
          <span class="text-[13px] text-muted">{{ hover !== null ? `${dayLabel(s.plays.days[hover].day)} · ${t('stats.playsN', { n: s.plays.days[hover].plays })}` : t('stats.peak', { n: peak }) }}</span>
        </div>
        <div class="relative">
          <!-- a recessive guide at the peak -->
          <div class="pointer-events-none absolute inset-x-0 top-0 border-t border-dashed border-line" aria-hidden="true" />
          <div class="flex h-40 items-end gap-[2px]" role="list" :aria-label="t('stats.daily', { n: s.days })" @mouseleave="hover = null">
            <button
              v-for="(d, i) in s.plays.days"
              :key="d.day"
              type="button"
              role="listitem"
              class="group flex h-full min-w-0 flex-1 items-end"
              :aria-label="`${dayLabel(d.day)}: ${t('stats.playsN', { n: d.plays })}`"
              @mouseenter="hover = i"
              @focus="hover = i"
              @blur="hover = null"
            >
              <span
                class="w-full rounded-t-[4px] transition-opacity"
                :class="hover === null || hover === i ? 'bg-accent' : 'bg-accent opacity-40'"
                :style="{ height: d.plays ? `${Math.max(3, (d.plays / peak) * 100)}%` : '0' }"
              />
            </button>
          </div>
          <div class="mt-1.5 flex justify-between border-t border-line pt-1.5 font-display text-[11px] text-muted">
            <span v-for="i in [0, 7, 14, 21, s.plays.days.length - 1]" :key="i">{{ dayLabel(s.plays.days[i].day) }}</span>
          </div>
        </div>
      </section>

      <div class="grid gap-5 lg:grid-cols-2">
        <!-- top songs / artists / people -->
        <section v-for="list in [
          { title: t('stats.topTracks', { n: s.days }), rows: s.plays.top_tracks.map((x) => ({ key: x.id, name: x.title, sub: x.artist, n: x.plays, to: undefined as string | undefined })) },
          { title: t('stats.topArtists', { n: s.days }), rows: s.plays.top_artists.map((x) => ({ key: x.id, name: x.name, sub: '', n: x.plays, to: `/artists/${x.id}` })) },
          { title: t('stats.perUser', { n: s.days }), rows: s.plays.per_user.map((x) => ({ key: x.id, name: x.name, sub: t('stats.hours', { n: x.hours }), n: x.plays, to: undefined })) },
        ]" :key="list.title" class="flex flex-col gap-3 rounded-2xl border border-line p-5">
          <h2 class="text-lg font-bold">{{ list.title }}</h2>
          <p v-if="!list.rows.length" class="text-[14px] font-light text-muted">{{ t('stats.none') }}</p>
          <ol class="flex flex-col gap-2.5">
            <li v-for="(r, i) in list.rows" :key="r.key" class="flex items-center gap-3">
              <span class="w-5 flex-none text-right font-display text-[13px] text-muted">{{ i + 1 }}</span>
              <span class="flex min-w-0 flex-1 flex-col gap-1">
                <span class="flex items-baseline justify-between gap-3">
                  <RouterLink v-if="r.to" :to="r.to" class="truncate text-[15px] hover:underline">{{ r.name }}</RouterLink>
                  <span v-else class="truncate text-[15px]">{{ r.name }}<span v-if="r.sub" class="text-[13px] font-light text-muted"> · {{ r.sub }}</span></span>
                  <span class="flex-none font-display text-[13px] text-muted">{{ num(r.n) }}</span>
                </span>
                <span class="h-1.5 rounded-full bg-surface"><span class="block h-full rounded-full bg-accent" :style="{ width: `${(r.n / maxOf(list.rows.map((x) => ({ plays: x.n })), 'plays')) * 100}%` }" /></span>
              </span>
            </li>
          </ol>
        </section>

        <!-- formats and quality -->
        <section class="flex flex-col gap-3 rounded-2xl border border-line p-5">
          <h2 class="text-lg font-bold">{{ t('stats.formats') }}</h2>
          <ol class="flex flex-col gap-2.5">
            <li v-for="f in s.library.formats" :key="f.format" class="flex flex-col gap-1">
              <span class="flex items-baseline justify-between gap-3 text-[15px]">
                <span class="font-display uppercase">{{ f.format }}</span>
                <span class="font-display text-[13px] text-muted">{{ t('stats.tracksN', { n: num(f.tracks) }) }} · {{ size(f.bytes) }}</span>
              </span>
              <span class="h-1.5 rounded-full bg-surface"><span class="block h-full rounded-full bg-accent" :style="{ width: `${(f.tracks / maxOf(s.library.formats, 'tracks')) * 100}%` }" /></span>
            </li>
          </ol>
          <h3 class="mt-2 font-medium">{{ t('stats.quality') }}</h3>
          <div class="flex flex-col gap-1.5 text-[14px]">
            <div v-for="q in quality" :key="q.key" class="flex items-center justify-between gap-3">
              <span>{{ t(`stats.quality_${q.key}`) }}</span>
              <span class="font-display text-[13px] text-muted">{{ t('stats.albumsN', { n: num(q.n) }) }} · {{ q.pct }}%</span>
            </div>
          </div>
        </section>
      </div>

      <div class="grid gap-5 lg:grid-cols-2">
        <section class="flex flex-col gap-2 rounded-2xl border border-line p-5">
          <h2 class="mb-1 text-lg font-bold">{{ t('stats.library') }}</h2>
          <div v-for="c in checks" :key="c.label" class="flex items-center justify-between gap-3 text-[14px]">
            <span>{{ c.label }}</span><span class="font-display text-muted">{{ num(c.n) }}</span>
          </div>
        </section>
        <section class="flex flex-col gap-2 rounded-2xl border border-line p-5">
          <h2 class="mb-1 text-lg font-bold">{{ t('stats.storage') }}</h2>
          <div v-for="k in (['database', 'covers', 'transcode'] as const)" :key="k" class="flex items-center justify-between gap-3 text-[14px]">
            <span>{{ t(`stats.storage_${k}`) }}</span><span class="font-display text-muted">{{ size(s.storage[k]) }}</span>
          </div>
          <p class="mt-1 text-[12px] font-light text-muted">{{ t('stats.note') }}</p>
        </section>
      </div>
    </template>
  </div>
</template>
