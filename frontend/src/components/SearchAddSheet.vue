<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Check, ChevronLeft, ChevronRight, Plus, Search } from '@lucide/vue'
import { api, query } from '../api'
import { errorMessage } from '../i18n'
import { useLibrary } from '../stores/library'
import { useUi } from '../stores/ui'
import type { Album, Artist, Page, Track, VideoListItem } from '../types'
import ArtistPhoto from './ArtistPhoto.vue'
import BaseModal from './BaseModal.vue'
import CoverArt from './CoverArt.vue'
import TrackAddRow from './TrackAddRow.vue'
import VideoThumb from './VideoThumb.vue'

// Adding to a playlist from a search: songs (a playlist) or music videos (a video playlist). Each
// result is added with its +; what is in the list already shows a check. The sheet stays open for more.
// Songs: the results by kind — songs, albums, artists (a few of each, or all of one kind, page by
// page); an album or an artist opens its songs here, to add one by one or all at once.
const props = defineProps<{ kind: 'tracks' | 'videos'; listId: number; listName: string; has: number[] }>()
const emit = defineEmits<{ close: []; added: [] }>()
const { t } = useI18n()
const library = useLibrary()
const ui = useUi()
const q = ref('')
const inList = ref(new Set(props.has))
const busy = ref(false)
const error = ref('')
let timer: number | undefined
let asked = 0
let changed = false

type Kind = 'tracks' | 'albums' | 'artists'
const KINDS: Kind[] = ['tracks', 'albums', 'artists']
const tab = ref<'all' | Kind>('all')
const FEW = { tracks: 6, albums: 4, artists: 4 } // each kind's first few, on "all"
const PAGE = 40
const found = ref<{ tracks: Page<Track>; albums: Page<Album>; artists: Page<Artist> }>({
  tracks: { items: [], total: 0 },
  albums: { items: [], total: 0 },
  artists: { items: [], total: 0 },
})
const videos = ref<Page<VideoListItem>>({ items: [], total: 0 })
const nothing = computed(() => KINDS.every((k) => !found.value[k].total))

function fetchKind(k: Kind, text: string, limit: number, offset = 0): Promise<Page<Track> | Page<Album> | Page<Artist>> {
  if (k === 'tracks') return api<Page<Track>>(`/tracks${query({ q: text, limit, offset, sort: 'relevance' })}`)
  if (k === 'albums') return api<Page<Album>>(`/albums${query({ q: text, limit, offset, sort: 'title' })}`)
  return api<Page<Artist>>(`/artists${query({ q: text, limit, offset })}`)
}

async function search() {
  const text = q.value.trim()
  const mine = ++asked
  busy.value = true
  error.value = ''
  try {
    if (props.kind === 'videos') {
      // videos: the newest ones before anything is typed (there are not many)
      const r = await api<Page<VideoListItem>>(`/videos${query({ q: text || undefined, limit: 60 })}`)
      if (mine === asked) videos.value = r
      return
    }
    if (!text) {
      found.value = { tracks: { items: [], total: 0 }, albums: { items: [], total: 0 }, artists: { items: [], total: 0 } }
      return
    }
    const kinds = tab.value === 'all' ? KINDS : [tab.value]
    const pages = await Promise.all(kinds.map((k) => fetchKind(k, text, tab.value === 'all' ? FEW[k] : PAGE)))
    if (mine !== asked) return
    const next = { ...found.value }
    // on one kind's tab the others keep their counts (shown on the tabs)
    kinds.forEach((k, i) => ((next as Record<Kind, unknown>)[k] = pages[i]))
    found.value = next
  } catch (e) {
    error.value = errorMessage(e)
  } finally {
    if (mine === asked) busy.value = false
  }
}
async function more(k: Kind) {
  const text = q.value.trim()
  const mine = asked
  busy.value = true
  try {
    const page = await fetchKind(k, text, PAGE, found.value[k].items.length)
    if (mine !== asked) return
    const cur = found.value[k]
    found.value = { ...found.value, [k]: { items: [...cur.items, ...page.items], total: page.total } }
  } catch (e) {
    error.value = errorMessage(e)
  } finally {
    busy.value = false
  }
}
async function moreVideos() {
  const r = await api<Page<VideoListItem>>(`/videos${query({ q: q.value.trim() || undefined, limit: 60, offset: videos.value.items.length })}`).catch(() => null)
  if (r) videos.value = { items: [...videos.value.items, ...r.items], total: r.total }
}
watch(q, () => {
  clearTimeout(timer)
  opened.value = null
  timer = window.setTimeout(search, 250)
})
watch(tab, () => search())
onMounted(() => {
  if (props.kind === 'videos') search()
  document.getElementById('add-q')?.focus()
})
onUnmounted(() => clearTimeout(timer))

// an album or an artist opened here: its songs
const opened = ref<{ title: string; sub: string; tracks: Track[] } | null>(null)
async function open(what: { album?: Album; artist?: Artist }) {
  busy.value = true
  try {
    const r = await api<Page<Track>>(`/tracks${query(what.album ? { album_id: what.album.id, sort: 'album', limit: 500 } : { artist_id: what.artist!.id, sort: 'album', limit: 500 })}`)
    opened.value = what.album
      ? { title: what.album.title, sub: what.album.artist || t('common.unknownArtist'), tracks: r.items }
      : { title: what.artist!.name, sub: t('common.tracks', r.total), tracks: r.items }
  } catch (e) {
    error.value = errorMessage(e)
  } finally {
    busy.value = false
  }
}
const notYet = computed(() => opened.value?.tracks.filter((x) => !x.missing && !inList.value.has(x.id)) ?? [])

async function add(track: Track) {
  try {
    await library.addToPlaylist(props.listId, [track])
    inList.value = new Set(inList.value).add(track.id)
    changed = true
  } catch (e) {
    error.value = errorMessage(e)
  }
}
async function addAll() {
  const tracks = notYet.value
  if (!tracks.length) return
  try {
    const r = await library.addToPlaylist(props.listId, tracks)
    const next = new Set(inList.value)
    tracks.forEach((x) => next.add(x.id))
    inList.value = next
    changed = true
    ui.notify(t('playlists.addedAll', { n: r.added }))
  } catch (e) {
    error.value = errorMessage(e)
  }
}
async function addVideo(id: number) {
  try {
    await api(`/video-playlists/${props.listId}/videos`, { method: 'POST', body: { video_ids: [id] } })
    inList.value = new Set(inList.value).add(id)
    changed = true
  } catch (e) {
    error.value = errorMessage(e)
  }
}
function close() {
  if (changed) emit('added')
  emit('close')
}
</script>

<template>
  <BaseModal wide :title="kind === 'tracks' ? t('playlists.addSongs', { name: listName }) : t('videos.addVideos', { name: listName })" @close="close">
    <div class="flex flex-col gap-3">
      <form class="flex h-11 items-center gap-2 rounded-full bg-surface px-4" role="search" @submit.prevent="search">
        <Search :size="18" :stroke-width="1.5" class="text-muted" aria-hidden="true" />
        <label for="add-q" class="sr-only">{{ t('search.label') }}</label>
        <input id="add-q" v-model="q" type="search" maxlength="200" :placeholder="kind === 'tracks' ? t('search.placeholder') : t('videos.searchVideos')" class="min-w-0 flex-1 bg-transparent text-[15px] outline-none" />
      </form>
      <p v-if="error" class="text-[14px] text-danger" role="alert">{{ error }}</p>

      <!-- songs -->
      <template v-if="kind === 'tracks'">
        <!-- an album's or an artist's songs -->
        <template v-if="opened">
          <div class="flex items-center gap-2">
            <button type="button" class="-ml-2 grid size-10 flex-none place-items-center rounded-full hover:bg-surface" :aria-label="t('nav.back')" @click="opened = null">
              <ChevronLeft :size="22" :stroke-width="1.6" />
            </button>
            <span class="flex min-w-0 flex-1 flex-col">
              <span class="truncate text-[16px] font-semibold">{{ opened.title }}</span>
              <span class="truncate text-[13px] text-muted">{{ opened.sub }}</span>
            </span>
            <button type="button" class="flex h-9 flex-none items-center gap-1 rounded-full bg-ink px-3.5 text-[14px] text-on-ink disabled:opacity-40" :disabled="!notYet.length" @click="addAll">
              <Plus :size="16" :stroke-width="1.8" />{{ t('playlists.addAll') }}
            </button>
          </div>
          <ul class="flex flex-col">
            <TrackAddRow v-for="tr in opened.tracks" :key="tr.id" :track="tr" :added="inList.has(tr.id)" @add="add(tr)" />
          </ul>
        </template>

        <template v-else>
          <p v-if="!q.trim()" class="text-[14px] text-muted">{{ t('playlists.addHint') }}</p>
          <template v-else>
            <!-- by kind -->
            <div class="-mx-1 flex gap-1.5 overflow-x-auto px-1 [scrollbar-width:none]" role="tablist">
              <button
                v-for="k in (['all', ...KINDS] as const)"
                :key="k"
                type="button"
                role="tab"
                :aria-selected="tab === k"
                class="h-9 flex-none rounded-full border px-3.5 text-[14px]"
                :class="tab === k ? 'border-ink bg-ink text-on-ink' : 'border-line-strong'"
                @click="tab = k"
              >
                {{ t(`search.tab_${k}`) }}<span v-if="k !== 'all' && found[k].total" class="ml-1 opacity-60">{{ found[k].total }}</span>
              </button>
            </div>
            <p v-if="!busy && (tab === 'all' ? nothing : !found[tab].total)" class="text-[14px] text-muted">{{ t('search.noResults') }}</p>

            <div class="flex flex-col gap-4" :class="busy ? 'opacity-60' : ''">
              <!-- songs -->
              <section v-if="(tab === 'all' || tab === 'tracks') && found.tracks.items.length" class="flex flex-col gap-1">
                <h3 v-if="tab === 'all'" class="flex items-center justify-between px-2 text-[15px] font-bold">
                  {{ t('search.tab_tracks') }}
                  <button v-if="found.tracks.total > found.tracks.items.length" type="button" class="flex items-center text-[13px] font-normal text-muted hover:text-ink" @click="tab = 'tracks'">{{ t('playlists.seeAll', { n: found.tracks.total }) }}<ChevronRight :size="16" /></button>
                </h3>
                <ul class="flex flex-col">
                  <TrackAddRow v-for="tr in found.tracks.items" :key="tr.id" :track="tr" :added="inList.has(tr.id)" @add="add(tr)" />
                </ul>
              </section>
              <!-- albums: open one for its songs -->
              <section v-if="(tab === 'all' || tab === 'albums') && found.albums.items.length" class="flex flex-col gap-1">
                <h3 v-if="tab === 'all'" class="flex items-center justify-between px-2 text-[15px] font-bold">
                  {{ t('search.tab_albums') }}
                  <button v-if="found.albums.total > found.albums.items.length" type="button" class="flex items-center text-[13px] font-normal text-muted hover:text-ink" @click="tab = 'albums'">{{ t('playlists.seeAll', { n: found.albums.total }) }}<ChevronRight :size="16" /></button>
                </h3>
                <ul class="flex flex-col">
                  <li v-for="a in found.albums.items" :key="a.id">
                    <button type="button" class="flex w-full items-center gap-3 rounded-xl px-2 py-1.5 text-left hover:bg-surface" @click="open({ album: a })">
                      <CoverArt :album-id="a.id" :has-cover="a.has_cover" :version="a.cover_v" rounded="rounded-md" class="size-11 flex-none" />
                      <span class="flex min-w-0 flex-1 flex-col">
                        <span class="truncate text-[15px]">{{ a.title }}</span>
                        <span class="truncate text-[13px] text-muted">{{ a.artist || t('common.unknownArtist') }}<template v-if="a.year"> · {{ a.year }}</template> · {{ t('common.tracks', a.track_count) }}</span>
                      </span>
                      <ChevronRight :size="18" class="flex-none text-subtle" />
                    </button>
                  </li>
                </ul>
              </section>
              <!-- artists: open one for their songs -->
              <section v-if="(tab === 'all' || tab === 'artists') && found.artists.items.length" class="flex flex-col gap-1">
                <h3 v-if="tab === 'all'" class="flex items-center justify-between px-2 text-[15px] font-bold">
                  {{ t('search.tab_artists') }}
                  <button v-if="found.artists.total > found.artists.items.length" type="button" class="flex items-center text-[13px] font-normal text-muted hover:text-ink" @click="tab = 'artists'">{{ t('playlists.seeAll', { n: found.artists.total }) }}<ChevronRight :size="16" /></button>
                </h3>
                <ul class="flex flex-col">
                  <li v-for="a in found.artists.items" :key="a.id">
                    <button type="button" class="flex w-full items-center gap-3 rounded-xl px-2 py-1.5 text-left hover:bg-surface" @click="open({ artist: a })">
                      <ArtistPhoto :artist-id="a.id" :name="a.name" :version="a.image_v" class="size-11 flex-none" />
                      <span class="flex min-w-0 flex-1 flex-col">
                        <span class="truncate text-[15px]">{{ a.name }}</span>
                        <span class="truncate text-[13px] text-muted">{{ t('common.tracks', a.track_count) }}</span>
                      </span>
                      <ChevronRight :size="18" class="flex-none text-subtle" />
                    </button>
                  </li>
                </ul>
              </section>
              <!-- one kind: the next page -->
              <button
                v-if="tab !== 'all' && found[tab].items.length < found[tab].total"
                type="button"
                class="h-10 self-center rounded-full border border-line-strong px-5 text-[14px] disabled:opacity-40"
                :disabled="busy"
                @click="more(tab)"
              >
                {{ t('common.loadMore') }}
              </button>
            </div>
          </template>
        </template>
      </template>

      <!-- music videos -->
      <template v-else>
        <p v-if="!busy && !videos.items.length" class="text-[14px] text-muted">{{ t('search.noResults') }}</p>
        <ul class="flex flex-col" :class="busy ? 'opacity-60' : ''">
          <li v-for="v in videos.items" :key="v.id" class="flex items-center gap-3 rounded-xl px-2 py-1.5 hover:bg-surface">
            <span class="relative aspect-video w-24 flex-none overflow-hidden rounded-lg bg-surface"><VideoThumb :video="v" :icon="18" /></span>
            <span class="flex min-w-0 flex-1 flex-col">
              <span class="line-clamp-2 text-[14px] leading-snug">{{ v.title }}</span>
              <span class="truncate text-[12px] text-muted">{{ t(`videos.kinds.${v.kind}`) }}<template v-if="v.target"> · {{ v.target.artist || v.target.title }}</template></span>
            </span>
            <span v-if="inList.has(v.id)" class="grid size-10 flex-none place-items-center text-accent" :aria-label="t('playlists.inList')"><Check :size="20" :stroke-width="2" /></span>
            <button v-else type="button" class="grid size-10 flex-none place-items-center rounded-full border border-line-strong hover:border-ink" :aria-label="`${t('common.add')}: ${v.title}`" @click="addVideo(v.id)">
              <Plus :size="18" :stroke-width="1.8" />
            </button>
          </li>
        </ul>
        <button v-if="videos.items.length < videos.total" type="button" class="h-10 self-center rounded-full border border-line-strong px-5 text-[14px]" @click="moreVideos">{{ t('common.loadMore') }}</button>
      </template>
    </div>
  </BaseModal>
</template>
