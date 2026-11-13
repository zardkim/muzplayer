<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ChevronLeft } from '@lucide/vue'
import { api } from '../api'
import { errorMessage } from '../i18n'
import PageHeader from '../components/PageHeader.vue'

// Admin → statistics (backend stats.py): the library, the people, what was played in the last
// 30 days, the disk this app uses, the audiobooks (listening) and the music videos. Headline numbers as tiles; one-series bars in the accent
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
  books: {
    books: number; hours: number; bytes: number; authors: number; series: number; chapters: number
    listeners: number; in_progress: number; finished: number; listened_hours: number; active_days: number
    top: { id: number; title: string; authors: string; listeners: number; finished: number }[]
    per_user: { id: number; name: string; books: number; finished: number; hours: number }[]
  }
  videos: {
    videos: number; youtube: number; local: number; local_hours: number; with_album: number; added_days: number
    favorites: number; playlists: number; playlist_items: number
    kinds: { kind: string; videos: number }[]
    top: { id: number; title: string; channel: string; youtube: boolean; likes: number }[]
    channels: { name: string; videos: number }[]
  }
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
// phone: each ranking shows its first few until opened (the page is long otherwise)
const FEW = 5
const opened = ref(new Set<string>())
const maxOf = (list: { plays?: number; tracks?: number }[], key: 'plays' | 'tracks') => Math.max(1, ...list.map((x) => x[key] ?? 0))
const quality = computed(() => {
  const q = s.value?.library.quality
  if (!q) return []
  const total = Math.max(1, q.hires + q.lossless + q.lossy)
  return (['hires', 'lossless', 'lossy'] as const).map((k) => ({ key: k, n: q[k], pct: Math.round((q[k] / total) * 100) }))
})
// audiobooks and music videos: a few numbers each, then their lists
const bookTiles = computed(() => {
  const b = s.value?.books
  if (!b) return []
  return [
    { label: t('stats.bookCount'), value: num(b.books), sub: t('stats.hours', { n: num(b.hours) }) },
    { label: t('stats.bookAuthors'), value: num(b.authors), sub: t('stats.bookSeries', { n: num(b.series) }) },
    { label: t('stats.size'), value: size(b.bytes), sub: t('stats.bookChapters', { n: num(b.chapters) }) },
    { label: t('stats.bookListened'), value: t('stats.hoursShort', { n: num(b.listened_hours) }), sub: t('stats.bookListeners', { n: b.listeners }) },
    { label: t('stats.bookInProgress'), value: num(b.in_progress), sub: t('stats.bookActive', { n: s.value!.days, m: b.active_days }) },
    { label: t('stats.bookFinished'), value: num(b.finished), sub: '' },
  ]
})
const videoTiles = computed(() => {
  const v = s.value?.videos
  if (!v) return []
  return [
    { label: t('stats.videoCount'), value: num(v.videos), sub: t('stats.videoAdded', { n: s.value!.days, m: v.added_days }) },
    { label: t('stats.videoYoutube'), value: num(v.youtube), sub: '' },
    { label: t('stats.videoLocal'), value: num(v.local), sub: t('stats.hours', { n: num(v.local_hours) }) },
    { label: t('stats.videoAlbum'), value: num(v.with_album), sub: '' },
    { label: t('stats.videoFavorites'), value: num(v.favorites), sub: '' },
    { label: t('stats.videoPlaylists'), value: num(v.playlists), sub: t('stats.videoItems', { n: num(v.playlist_items) }) },
  ]
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
  <div class="flex flex-col gap-5 md:gap-8">
    <!-- (a phone has the back button above already) -->
    <RouterLink to="/admin" class="-mb-4 flex items-center gap-1 self-start text-[14px] text-muted hover:text-ink max-md:hidden"><ChevronLeft :size="16" />{{ t('admin.title') }}</RouterLink>
    <PageHeader :title="t('stats.title')" />
    <p v-if="error" class="font-light text-muted">{{ error }}</p>
    <p v-else-if="!s" class="font-light text-muted">{{ t('common.loading') }}</p>
    <template v-else>
      <!-- headline numbers -->
      <div class="grid grid-cols-3 gap-2 md:gap-3 xl:grid-cols-6">
        <div v-for="x in tiles" :key="x.label" class="flex min-w-0 flex-col gap-0.5 rounded-2xl bg-surface px-3 py-2.5 md:gap-1 md:px-4 md:py-3.5">
          <span class="truncate text-[12px] text-muted md:text-[13px]">{{ x.label }}</span>
          <span class="truncate font-display text-[19px] font-bold leading-tight md:text-[26px]">{{ x.value }}</span>
          <span class="truncate text-[11px] text-muted md:text-[12px]">{{ x.sub }}</span>
        </div>
      </div>

      <!-- plays per day -->
      <section class="flex min-w-0 flex-col gap-3 rounded-2xl border border-line p-4 md:p-5">
        <div class="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5">
          <h2 class="min-w-0 text-[16px] font-bold md:text-lg">{{ t('stats.daily', { n: s.days }) }}</h2>
          <span class="text-[13px] text-muted">{{ hover !== null ? `${dayLabel(s.plays.days[hover].day)} · ${t('stats.playsN', { n: s.plays.days[hover].plays })}` : t('stats.peak', { n: peak }) }}</span>
        </div>
        <div class="relative min-w-0 overflow-hidden">
          <!-- a recessive guide at the peak -->
          <div class="pointer-events-none absolute inset-x-0 top-0 border-t border-dashed border-line" aria-hidden="true" />
          <!-- plain boxes, not buttons: Safari won't shrink a button below its own minimum, and thirty of
               them then run past a phone's edge -->
          <div class="flex h-28 items-end gap-[2px] md:h-40" role="list" :aria-label="t('stats.daily', { n: s.days })" @mouseleave="hover = null">
            <div
              v-for="(d, i) in s.plays.days"
              :key="d.day"
              role="listitem"
              tabindex="0"
              class="flex h-full w-0 min-w-0 flex-1 items-end outline-none"
              :aria-label="`${dayLabel(d.day)}: ${t('stats.playsN', { n: d.plays })}`"
              @mouseenter="hover = i"
              @touchstart.passive="hover = i"
              @focus="hover = i"
              @blur="hover = null"
            >
              <span
                class="w-full rounded-t-[4px] transition-opacity"
                :class="hover === null || hover === i ? 'bg-accent' : 'bg-accent opacity-40'"
                :style="{ height: d.plays ? `${Math.max(3, (d.plays / peak) * 100)}%` : '0' }"
              />
            </div>
          </div>
          <!-- dates under it: five on a wide screen, three on a phone (they never push past its edge) -->
          <div class="mt-1.5 flex justify-between gap-2 overflow-hidden whitespace-nowrap border-t border-line pt-1.5 font-display text-[11px] text-muted">
            <span v-for="(i, k) in [0, 7, 14, 21, s.plays.days.length - 1]" :key="i" :class="k === 1 || k === 3 ? 'max-md:hidden' : ''">{{ dayLabel(s.plays.days[i].day) }}</span>
          </div>
        </div>
      </section>

      <div class="grid grid-cols-[minmax(0,1fr)] gap-5 lg:grid-cols-[repeat(2,minmax(0,1fr))]">
        <!-- top songs / artists / people -->
        <section v-for="list in [
          { title: t('stats.topTracks', { n: s.days }), rows: s.plays.top_tracks.map((x) => ({ key: x.id, name: x.title, sub: x.artist, n: x.plays, to: undefined as string | undefined })) },
          { title: t('stats.topArtists', { n: s.days }), rows: s.plays.top_artists.map((x) => ({ key: x.id, name: x.name, sub: '', n: x.plays, to: `/artists/${x.id}` })) },
          { title: t('stats.perUser', { n: s.days }), rows: s.plays.per_user.map((x) => ({ key: x.id, name: x.name, sub: t('stats.hours', { n: x.hours }), n: x.plays, to: undefined })) },
        ]" :key="list.title" class="flex min-w-0 flex-col gap-3 rounded-2xl border border-line p-4 md:p-5">
          <h2 class="text-[16px] font-bold md:text-lg">{{ list.title }}</h2>
          <p v-if="!list.rows.length" class="text-[14px] font-light text-muted">{{ t('stats.none') }}</p>
          <ol class="flex flex-col gap-2 md:gap-2.5">
            <li v-for="(r, i) in list.rows" :key="r.key" class="flex items-center gap-3" :class="i >= FEW && !opened.has(list.title) ? 'max-md:hidden' : ''">
              <span class="w-5 flex-none text-right font-display text-[13px] text-muted">{{ i + 1 }}</span>
              <span class="flex min-w-0 flex-1 flex-col gap-1">
                <span class="flex items-baseline justify-between gap-3">
                  <RouterLink v-if="r.to" :to="r.to" class="truncate text-[14px] hover:underline md:text-[15px]">{{ r.name }}</RouterLink>
                  <span v-else class="truncate text-[14px] md:text-[15px]">{{ r.name }}<span v-if="r.sub" class="text-[13px] font-light text-muted"> · {{ r.sub }}</span></span>
                  <span class="flex-none font-display text-[13px] text-muted">{{ num(r.n) }}</span>
                </span>
                <span class="h-1.5 rounded-full bg-surface"><span class="block h-full rounded-full bg-accent" :style="{ width: `${(r.n / maxOf(list.rows.map((x) => ({ plays: x.n })), 'plays')) * 100}%` }" /></span>
              </span>
            </li>
          </ol>
          <button
            v-if="list.rows.length > FEW"
            type="button"
            class="self-center text-[13px] text-muted hover:text-ink md:hidden"
            :aria-expanded="opened.has(list.title)"
            @click="opened = new Set(opened.has(list.title) ? [...opened].filter((k) => k !== list.title) : [...opened, list.title])"
          >
            {{ opened.has(list.title) ? t('stats.showFewer') : t('stats.showAll', { n: list.rows.length }) }}
          </button>
        </section>

        <!-- formats and quality -->
        <section class="flex min-w-0 flex-col gap-3 rounded-2xl border border-line p-4 md:p-5">
          <h2 class="text-[16px] font-bold md:text-lg">{{ t('stats.formats') }}</h2>
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

      <div class="grid grid-cols-[minmax(0,1fr)] gap-5 lg:grid-cols-[repeat(2,minmax(0,1fr))]">
        <section class="flex min-w-0 flex-col gap-2 rounded-2xl border border-line p-4 md:p-5">
          <h2 class="mb-1 text-[16px] font-bold md:text-lg">{{ t('stats.library') }}</h2>
          <div v-for="c in checks" :key="c.label" class="flex items-center justify-between gap-3 text-[14px]">
            <span>{{ c.label }}</span><span class="font-display text-muted">{{ num(c.n) }}</span>
          </div>
        </section>
        <section class="flex min-w-0 flex-col gap-2 rounded-2xl border border-line p-4 md:p-5">
          <h2 class="mb-1 text-[16px] font-bold md:text-lg">{{ t('stats.storage') }}</h2>
          <div v-for="k in (['database', 'covers', 'transcode'] as const)" :key="k" class="flex items-center justify-between gap-3 text-[14px]">
            <span>{{ t(`stats.storage_${k}`) }}</span><span class="font-display text-muted">{{ size(s.storage[k]) }}</span>
          </div>
          <p class="mt-1 text-[12px] font-light text-muted">{{ t('stats.note') }}</p>
        </section>
      </div>

      <!-- audiobooks -->
      <template v-if="s.books.books">
        <h2 class="-mb-2 mt-2 text-[19px] font-bold md:text-[22px]">{{ t('stats.booksTitle') }}</h2>
        <div class="grid grid-cols-3 gap-2 md:gap-3 xl:grid-cols-6">
          <div v-for="x in bookTiles" :key="x.label" class="flex min-w-0 flex-col gap-0.5 rounded-2xl bg-surface px-3 py-2.5 md:gap-1 md:px-4 md:py-3.5">
            <span class="truncate text-[12px] text-muted md:text-[13px]">{{ x.label }}</span>
            <span class="truncate font-display text-[19px] font-bold leading-tight md:text-[26px]">{{ x.value }}</span>
            <span class="truncate text-[11px] text-muted md:text-[12px]">{{ x.sub }}</span>
          </div>
        </div>
        <div class="grid grid-cols-[minmax(0,1fr)] gap-5 lg:grid-cols-[repeat(2,minmax(0,1fr))]">
          <section v-for="list in [
            { title: t('stats.bookTop'), rows: s.books.top.map((x) => ({ key: x.id, name: x.title, sub: x.authors, n: x.listeners, note: t('stats.bookTopNote', { n: x.listeners, f: x.finished }), to: `/books/${x.id}` })) },
            { title: t('stats.bookPerUser'), rows: s.books.per_user.map((x) => ({ key: x.id, name: x.name, sub: t('stats.hours', { n: x.hours }), n: x.books, note: t('stats.bookUserNote', { n: x.books, f: x.finished }), to: undefined as string | undefined })) },
          ]" :key="list.title" class="flex min-w-0 flex-col gap-3 rounded-2xl border border-line p-4 md:p-5">
            <h2 class="text-[16px] font-bold md:text-lg">{{ list.title }}</h2>
            <p v-if="!list.rows.length" class="text-[14px] font-light text-muted">{{ t('stats.bookNone') }}</p>
            <ol class="flex flex-col gap-2 md:gap-2.5">
              <li v-for="(r, i) in list.rows" :key="r.key" class="flex items-center gap-3">
                <span class="w-5 flex-none text-right font-display text-[13px] text-muted">{{ i + 1 }}</span>
                <span class="flex min-w-0 flex-1 flex-col gap-1">
                  <span class="flex items-baseline justify-between gap-3">
                    <RouterLink v-if="r.to" :to="r.to" class="truncate text-[14px] hover:underline md:text-[15px]">{{ r.name }}<span v-if="r.sub" class="text-[13px] font-light text-muted"> · {{ r.sub }}</span></RouterLink>
                    <span v-else class="truncate text-[14px] md:text-[15px]">{{ r.name }}<span v-if="r.sub" class="text-[13px] font-light text-muted"> · {{ r.sub }}</span></span>
                    <span class="flex-none font-display text-[13px] text-muted">{{ r.note }}</span>
                  </span>
                  <span class="h-1.5 rounded-full bg-surface"><span class="block h-full rounded-full bg-accent" :style="{ width: `${(r.n / maxOf(list.rows.map((x) => ({ plays: x.n })), 'plays')) * 100}%` }" /></span>
                </span>
              </li>
            </ol>
          </section>
        </div>
      </template>

      <!-- music videos -->
      <template v-if="s.videos.videos">
        <h2 class="-mb-2 mt-2 text-[19px] font-bold md:text-[22px]">{{ t('stats.videosTitle') }}</h2>
        <div class="grid grid-cols-3 gap-2 md:gap-3 xl:grid-cols-6">
          <div v-for="x in videoTiles" :key="x.label" class="flex min-w-0 flex-col gap-0.5 rounded-2xl bg-surface px-3 py-2.5 md:gap-1 md:px-4 md:py-3.5">
            <span class="truncate text-[12px] text-muted md:text-[13px]">{{ x.label }}</span>
            <span class="truncate font-display text-[19px] font-bold leading-tight md:text-[26px]">{{ x.value }}</span>
            <span class="truncate text-[11px] text-muted md:text-[12px]">{{ x.sub }}</span>
          </div>
        </div>
        <div class="grid grid-cols-[minmax(0,1fr)] gap-5 lg:grid-cols-[repeat(2,minmax(0,1fr))]">
          <section class="flex min-w-0 flex-col gap-3 rounded-2xl border border-line p-4 md:p-5">
            <h2 class="text-[16px] font-bold md:text-lg">{{ t('stats.videoKinds') }}</h2>
            <ol class="flex flex-col gap-2.5">
              <li v-for="k in s.videos.kinds" :key="k.kind" class="flex flex-col gap-1">
                <span class="flex items-baseline justify-between gap-3 text-[15px]">
                  <span>{{ t(`videos.kinds.${k.kind}`) }}</span>
                  <span class="font-display text-[13px] text-muted">{{ t('stats.videosN', { n: num(k.videos) }) }}</span>
                </span>
                <span class="h-1.5 rounded-full bg-surface"><span class="block h-full rounded-full bg-accent" :style="{ width: `${(k.videos / Math.max(1, ...s.videos.kinds.map((x) => x.videos))) * 100}%` }" /></span>
              </li>
            </ol>
            <template v-if="s.videos.channels.length">
              <h3 class="mt-2 font-medium">{{ t('stats.videoChannels') }}</h3>
              <div v-for="c in s.videos.channels" :key="c.name" class="flex items-center justify-between gap-3 text-[14px]">
                <span class="truncate">{{ c.name }}</span><span class="flex-none font-display text-[13px] text-muted">{{ t('stats.videosN', { n: num(c.videos) }) }}</span>
              </div>
            </template>
          </section>
          <section class="flex min-w-0 flex-col gap-3 rounded-2xl border border-line p-4 md:p-5">
            <h2 class="text-[16px] font-bold md:text-lg">{{ t('stats.videoTop') }}</h2>
            <p v-if="!s.videos.top.length" class="text-[14px] font-light text-muted">{{ t('stats.videoNone') }}</p>
            <ol class="flex flex-col gap-2 md:gap-2.5">
              <li v-for="(v, i) in s.videos.top" :key="v.id" class="flex items-center gap-3">
                <span class="w-5 flex-none text-right font-display text-[13px] text-muted">{{ i + 1 }}</span>
                <span class="flex min-w-0 flex-1 flex-col gap-1">
                  <span class="flex items-baseline justify-between gap-3">
                    <span class="truncate text-[14px] md:text-[15px]">{{ v.title }}<span v-if="v.channel" class="text-[13px] font-light text-muted"> · {{ v.channel }}</span></span>
                    <span class="flex-none font-display text-[13px] text-muted">♥ {{ num(v.likes) }}</span>
                  </span>
                  <span class="h-1.5 rounded-full bg-surface"><span class="block h-full rounded-full bg-accent" :style="{ width: `${(v.likes / Math.max(1, ...s.videos.top.map((x) => x.likes))) * 100}%` }" /></span>
                </span>
              </li>
            </ol>
            <p class="mt-1 text-[12px] font-light text-muted">{{ t('stats.videoNote') }}</p>
          </section>
        </div>
      </template>
    </template>
  </div>
</template>
