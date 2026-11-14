<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ChevronLeft, ChevronRight, CircleCheck, CircleMinus, Heart, PenLine, Star, Tag } from '@lucide/vue'
import { api } from '../api'
import { neighbours } from '../albumNav'
import { useSwipe } from '../swipe'
import { duration } from '../format'
import { errorMessage } from '../i18n'
import { useAuth } from '../stores/auth'
import { useUi } from '../stores/ui'
import type { AlbumDetail } from '../types'
import AlbumNotesSheet from '../components/AlbumNotesSheet.vue'
import ExtractTagSheet from '../components/ExtractTagSheet.vue'
import CoverArt from '../components/CoverArt.vue'
import DownloadButton from '../components/DownloadButton.vue'
import PlayActions from '../components/PlayActions.vue'
import QualityBadge from '../components/QualityBadge.vue'
import StarRating from '../components/StarRating.vue'
import TrackList from '../components/TrackList.vue'
import Marquee from '../components/Marquee.vue'

const props = defineProps<{ id: string }>()
const { t } = useI18n()
const auth = useAuth()
const ui = useUi()
const router = useRouter()
const album = ref<AlbumDetail | null>(null)
const error = ref('')
const near = ref<Awaited<ReturnType<typeof neighbours>>>(null)

onMounted(async () => {
  neighbours(Number(props.id)).then((n) => (near.value = n))
  try {
    album.value = await api<AlbumDetail>(`/albums/${props.id}`)
  } catch (e) {
    error.value = errorMessage(e)
  }
})

// the previous / next album in the albums page's order (albumNav.ts): the arrows, ← →, and on a
// phone a sideways swipe the page follows. In place of this one (back goes to the list, not
// through every album seen).
function go(step: -1 | 1) {
  const id = step < 0 ? near.value?.prev : near.value?.next
  if (id) void router.replace({ name: 'album', params: { id } })
}
function onKey(e: KeyboardEvent) {
  if (e.altKey || e.ctrlKey || e.metaKey || notesOpen.value || (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight')) return
  if ((e.target as Element | null)?.closest('input, textarea, select, [contenteditable], [role=dialog], [role=slider]')) return
  e.preventDefault()
  go(e.key === 'ArrowLeft' ? -1 : 1)
}
onMounted(() => window.addEventListener('keydown', onKey))
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))
const shift = ref(0)
const swipe = useSwipe({
  axes: ['x'],
  allow: (_a, dx) => !!near.value && !!(dx > 0 ? near.value.prev : near.value.next),
  move: (_a, dx) => (shift.value = dx),
  end: ({ dx, fast }) => {
    shift.value = 0
    if (Math.abs(dx) > 90 || (fast && Math.abs(dx) > 30)) go(dx > 0 ? -1 : 1)
  },
})
// the album's own like and stars (each person's), saved right away
async function like() {
  const a = album.value!
  a.is_favorite = !a.is_favorite
  try {
    await api(`/favorites/albums/${a.id}`, { method: a.is_favorite ? 'PUT' : 'DELETE' })
  } catch (e) {
    a.is_favorite = !a.is_favorite
    ui.notify(errorMessage(e), true)
  }
}

async function rate(stars: number | null) {
  const a = album.value!
  const before = a.rating
  a.rating = stars
  try {
    await api(`/ratings/albums/${a.id}`, stars ? { method: 'PUT', body: { rating: stars } } : { method: 'DELETE' })
  } catch (e) {
    a.rating = before
    ui.notify(errorMessage(e), true)
  }
}

// what the download button saves (offline.ts)
const saveAs = computed(() => {
  const a = album.value!
  return {
    key: `album:${a.id}`, title: a.title || t('common.unknownAlbum'), subtitle: a.artist ?? '', link: `/albums/${a.id}`,
    cover: { albumId: a.id, hasCover: a.has_cover, v: a.cover_v }, tracks: a.tracks,
  }
})
// the introduction (under the title); admins update it (AlbumNotesSheet)
const notesOpen = ref(false)
// a song taken out of a music video (admins): its tags, edited in its file (ExtractTagSheet); saved,
// the song may be in another album now
const tagsOpen = ref(false)
function tagsSaved(r: { album_id: number | null }) {
  if (r.album_id && r.album_id !== album.value?.id) void router.replace({ name: 'album', params: { id: r.album_id } })
  else api<AlbumDetail>(`/albums/${props.id}`).then((a) => (album.value = a), () => {})
}
const notesFull = ref(false)
const longNotes = computed(() => (album.value?.description ?? '').length > 160 || (album.value?.description ?? '').split('\n').length > 3)
function notesSaved(text: string | null, source: string | null) {
  album.value!.description = text
  album.value!.description_source = source
}
const totalTime = computed(() => album.value?.tracks.reduce((s, x) => s + (x.duration ?? 0), 0) ?? 0)
const multiDisc = computed(() => new Set(album.value?.tracks.map((x) => x.disc_no ?? 1)).size > 1)
</script>

<template>
  <p v-if="error" class="font-light text-muted">{{ error }}</p>
  <div
    v-else-if="album"
    class="flex flex-col gap-7"
    :style="shift ? { transform: `translateX(${shift}px)`, opacity: 1 - Math.min(0.5, Math.abs(shift) / 600) } : undefined"
    :class="shift ? '' : 'transition-transform duration-200'"
    @touchstart="swipe.onTouchstart"
    @touchmove="swipe.onTouchmove"
    @touchend="swipe.onTouchend"
    @touchcancel="swipe.onTouchcancel"
  >
    <div v-if="near && (near.prev || near.next)" class="-mb-3 flex items-center justify-between">
      <button type="button" class="flex h-9 items-center gap-1 rounded-full pl-1.5 pr-3.5 text-sm text-muted hover:bg-surface hover:text-ink disabled:invisible" :disabled="!near.prev" :title="t('albums.prevAlbum') + ' (←)'" @click="go(-1)">
        <ChevronLeft :size="18" :stroke-width="1.7" />{{ t('albums.prevAlbum') }}
      </button>
      <span class="text-[12px] tabular-nums text-muted">{{ near.index + 1 }} / {{ near.total }}</span>
      <button type="button" class="flex h-9 items-center gap-1 rounded-full pl-3.5 pr-1.5 text-sm text-muted hover:bg-surface hover:text-ink disabled:invisible" :disabled="!near.next" :title="t('albums.nextAlbum') + ' (→)'" @click="go(1)">
        {{ t('albums.nextAlbum') }}<ChevronRight :size="18" :stroke-width="1.7" />
      </button>
    </div>
    <div class="flex flex-col gap-6 sm:flex-row sm:items-end sm:gap-8">
      <CoverArt :album-id="album.id" :has-cover="album.has_cover" :version="album.cover_v" size="large" rounded="rounded-xl" class="w-full shadow-[0_16px_40px_rgba(17,17,19,0.18)] sm:w-60" />
      <div class="flex min-w-0 flex-col gap-2.5">
        <span class="flex flex-wrap items-center gap-2"><span class="text-sm font-light text-muted"><template v-if="album.kind === 'unofficial' || album.kind === 'compilation' || album.kind === 'soundtrack' || album.kind === 'extracted'">{{ t(`albums.kind_${album.kind}`) }} · </template><template v-if="album.year">{{ album.year }} · </template>{{ t('common.tracks', album.tracks.length) }} · <span class="font-display">{{ duration(totalTime) }}</span></span><QualityBadge :quality="album.quality" large /></span>
        <Marquee as="h1" :text="album.title || t('common.unknownAlbum')" class="text-[30px] font-extrabold leading-tight tracking-tight md:text-[40px]" />
        <RouterLink v-if="album.artist_id" :to="{ name: 'artist', params: { id: album.artist_id } }" class="flex items-center text-lg font-medium">{{ album.artist }}<ChevronRight :size="18" :stroke-width="1.6" /></RouterLink>
        <span v-else class="text-lg text-muted">{{ t('common.unknownArtist') }}</span>
        <!-- the introduction: three lines under the title, the rest behind "more" -->
        <div v-if="album.description" class="flex max-w-2xl flex-col items-start gap-1">
          <p class="whitespace-pre-line text-[14px] font-light leading-relaxed text-soft" :class="notesFull ? '' : 'line-clamp-3'">{{ album.description }}</p>
          <span class="flex items-center gap-3">
            <button v-if="longNotes" type="button" class="text-[13px] font-medium text-muted hover:text-ink" @click="notesFull = !notesFull">{{ notesFull ? t('notes.less') : t('notes.more') }}</button>
            <!-- it has its introduction: said so (an admin can still change it from here) -->
            <button v-if="auth.user?.is_admin" type="button" class="flex items-center gap-1 text-[13px] text-accent hover:text-ink" :title="t('notes.update')" @click="notesOpen = true"><CircleCheck :size="13" :stroke-width="1.8" />{{ t('notes.updated') }}</button>
            <span v-else class="flex items-center gap-1 text-[13px] text-accent"><CircleCheck :size="13" :stroke-width="1.8" />{{ t('notes.updated') }}</span>
          </span>
        </div>
        <!-- none in its folder, on Bugs or Melon (looked up after a scan) -->
        <span v-else-if="album.kind !== 'chart'" class="flex items-center gap-3 text-[14px] font-light text-muted">
          <span class="flex items-center gap-1"><CircleMinus :size="14" :stroke-width="1.6" />{{ t('notes.noneShort') }}</span>
          <button v-if="auth.user?.is_admin" type="button" class="flex items-center gap-1 text-[13px] text-muted hover:text-ink" @click="notesOpen = true"><PenLine :size="13" :stroke-width="1.6" />{{ t('notes.add') }}</button>
        </span>
        <div class="flex flex-wrap items-center gap-x-2">
          <!-- no stars of one's own yet: Melon's score, faintly -->
          <StarRating :value="album.rating" :hint="album.site_ratings?.melon?.score ?? null" @rate="rate" />
          <span v-if="!album.rating && album.site_ratings?.melon" class="text-[13px] text-muted">{{ t('albums.melonHint') }}</span>
          <span v-else-if="!album.rating && album.track_rating_avg" class="text-[13px] text-muted">{{ t('albums.trackAvg', { n: album.track_rating_avg }) }}</span>
        </div>
        <!-- Melon's stars and Bugs' likes, looked up after a scan -->
        <span v-if="album.site_ratings" class="flex flex-wrap items-center gap-x-3 text-[13px] text-muted">
          <!-- Melon's score as stars (filled to the score, out of five) -->
          <a
            v-if="album.site_ratings.melon"
            :href="`https://www.melon.com/album/detail.htm?albumId=${album.site_ratings.melon.id}`"
            target="_blank"
            rel="noopener"
            class="flex items-center gap-1.5 hover:text-ink"
            :aria-label="t('albums.siteMelon', { score: album.site_ratings.melon.score.toFixed(1), count: album.site_ratings.melon.count.toLocaleString() })"
          >
            <span>{{ t('albums.siteMelonName') }}</span>
            <Star :size="14" :stroke-width="1.5" fill="currentColor" class="text-accent" aria-hidden="true" />
            <span class="tabular-nums text-ink/80">{{ album.site_ratings.melon.score.toFixed(1) }}</span>
            <span>({{ album.site_ratings.melon.count.toLocaleString() }})</span>
          </a>
          <!-- Bugs' likes with a heart -->
          <a
            v-if="album.site_ratings.bugs"
            :href="`https://music.bugs.co.kr/album/${album.site_ratings.bugs.id}`"
            target="_blank"
            rel="noopener"
            class="flex items-center gap-1.5 hover:text-ink"
            :aria-label="t('albums.siteBugs', { likes: album.site_ratings.bugs.likes.toLocaleString() })"
          >
            <span>{{ t('albums.siteBugsName') }}</span>
            <Heart :size="14" :stroke-width="1.5" fill="currentColor" class="text-[#ff3b28]" aria-hidden="true" />
            <span class="tabular-nums text-ink/80">{{ album.site_ratings.bugs.likes.toLocaleString() }}</span>
          </a>
        </span>
        <div class="mt-2 flex flex-wrap gap-2">
          <PlayActions :tracks="album.tracks" large />
          <button
            type="button"
            class="grid size-11 place-items-center rounded-full border border-line-strong"
            :class="album.is_favorite ? 'text-like' : ''"
            :aria-label="album.is_favorite ? t('common.favoriteRemove') : t('common.favoriteAdd')"
            :aria-pressed="album.is_favorite"
            @click="like"
          >
            <Heart :size="19" :stroke-width="1.4" :fill="album.is_favorite ? 'currentColor' : 'none'" />
          </button>
          <DownloadButton class="h-11" :list="saveAs" />
          <button v-if="auth.user?.is_admin && album.kind === 'extracted'" type="button" class="flex h-11 items-center gap-1.5 rounded-full border border-line-strong px-4 text-[14px] hover:border-ink" @click="tagsOpen = true">
            <Tag :size="16" :stroke-width="1.6" />{{ t('extractTags.edit') }}
          </button>
        </div>
      </div>
    </div>
    <TrackList :tracks="album.tracks" :show-cover="false" :show-album="false" :numbered="!multiDisc" video-buttons />
    <ExtractTagSheet v-if="tagsOpen" :tracks="album.tracks.map((x) => ({ id: x.id, title: x.title }))" @close="tagsOpen = false" @saved="tagsSaved" />
    <AlbumNotesSheet v-if="notesOpen" :album-id="album.id" :text="album.description" :source="album.description_source" @close="notesOpen = false" @saved="notesSaved" />
  </div>
</template>
