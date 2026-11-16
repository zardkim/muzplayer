<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, query } from '../api'
import { errorMessage } from '../i18n'
import { useUi } from '../stores/ui'
import type { Album, Page, Track } from '../types'
import BaseModal from './BaseModal.vue'
import ChoiceChip from './ChoiceChip.vue'
import CoverArt from './CoverArt.vue'
import SearchField from './SearchField.vue'

// Linking a video (ui.videoLink) to its song or its album (ui.videoLinkTab): a keyword (its title to
// begin with, without [MV], (Official Video) and the like; for an album also without "concert",
// "showcase"…), the library's songs or albums that match, one picked.
const { t } = useI18n()
const ui = useUi()
const video = ui.videoLink!
const tab = ref<'track' | 'album'>(ui.videoLinkTab)

const songWords = (s: string) =>
  s
    .replace(/[[(【（][^\])】）]*(?:m\/?v|official|video|lyric|4k|1080p|직캠|뮤비|teaser)[^\])】）]*[\])】）]/gi, ' ')
    .replace(/\b(?:official\s+(?:music\s+)?video|music\s+video|m\/?v|4k|1080p)\b/gi, ' ')
const albumWords = (s: string) =>
  songWords(s)
    .replace(/[[(【（][^\])】）]*[\])】）]/g, ' ')
    .replace(/\b(?:concert|live|showcase|full\s+album|highlight(?:\s+medley)?|trailer|teaser|making|documentary)\b/gi, ' ')
    .replace(/콘서트|쇼케이스|하이라이트|메들리|트레일러|티저|메이킹|라이브/g, ' ')
const tidy = (s: string) => s.replace(/\s+/g, ' ').trim()
const keyword = ref(tidy(tab.value === 'album' ? albumWords(video.title) : songWords(video.title)))

const tracks = ref<Track[] | null>(null)
const albums = ref<Album[] | null>(null)
const results = computed(() => (tab.value === 'album' ? albums.value : tracks.value))
const busy = ref(false)
const error = ref('')
let timer: number | undefined
let asked = 0

async function search() {
  const q = keyword.value.trim()
  if (!q) {
    tracks.value = albums.value = null
    return
  }
  const mine = ++asked
  busy.value = true
  error.value = ''
  try {
    if (tab.value === 'album') {
      const r = await api<Page<Album>>(`/albums${query({ q, limit: 30 })}`)
      if (mine === asked) albums.value = r.items
    } else {
      const r = await api<Page<Track>>(`/tracks${query({ q, limit: 30, sort: 'relevance' })}`)
      if (mine === asked) tracks.value = r.items
    }
  } catch (e) {
    error.value = errorMessage(e)
  } finally {
    if (mine === asked) busy.value = false
  }
}
watch(keyword, () => {
  clearTimeout(timer)
  timer = window.setTimeout(search, 300)
})
// the other tab: its own words from the title, searched again
watch(tab, (v) => {
  clearTimeout(timer)
  keyword.value = tidy(v === 'album' ? albumWords(video.title) : songWords(video.title))
  void search()
})
onMounted(search)
onUnmounted(() => clearTimeout(timer))

async function link(body: { track_id: number } | { album_id: number }, message: string) {
  try {
    await api(`/videos/${video.id}/link`, { method: 'POST', body })
    ui.notify(message)
    ui.videoLinked++
    ui.videoLink = null
  } catch (e) {
    error.value = errorMessage(e)
  }
}
const pickTrack = (tr: Track) => link({ track_id: tr.id }, t('videos.linkedTo', { song: `${tr.title} · ${tr.artist}` }))
const pickAlbum = (a: Album) => link({ album_id: a.id }, t('videos.linkedToAlbum', { album: `${a.title} · ${a.artist}` }))
</script>

<template>
  <BaseModal wide :title="tab === 'album' ? t('videos.linkAlbum') : t('videos.linkTitle')" @close="ui.videoLink = null">
    <div class="flex flex-col gap-3">
      <p class="truncate text-[14px] text-muted">{{ video.title }}</p>
      <div class="flex gap-2" role="tablist">
        <ChoiceChip tab small :active="tab === 'track'" @click="tab = 'track'">{{ t('videos.linkTabTrack') }}</ChoiceChip>
        <ChoiceChip tab small :active="tab === 'album'" @click="tab = 'album'">{{ t('videos.linkTabAlbum') }}</ChoiceChip>
      </div>
      <p class="text-[13px] text-muted">{{ tab === 'album' ? t('videos.linkAlbumHint') : t('videos.linkHint') }}</p>
      <SearchField v-model="keyword" large input-id="link-q" :placeholder="tab === 'album' ? t('videos.linkAlbumSearch') : t('videos.linkSearch')" @submit="search" />
      <p v-if="error" class="text-[14px] text-danger" role="alert">{{ error }}</p>
      <p v-else-if="busy && !results" class="text-[14px] text-muted" role="status">{{ t('common.loading') }}</p>
      <p v-else-if="results && !results.length" class="text-[14px] text-muted">{{ t('videos.linkNone') }}</p>
      <ul v-if="tab === 'track' && tracks?.length" class="flex flex-col" :class="busy ? 'opacity-60' : ''">
        <li v-for="tr in tracks" :key="tr.id">
          <button
            type="button"
            class="flex w-full items-center gap-3 rounded-xl px-2 py-2 text-left hover:bg-surface"
            :class="tr.id === video.track_id ? 'bg-accent-soft' : ''"
            :aria-current="tr.id === video.track_id"
            @click="pickTrack(tr)"
          >
            <CoverArt :album-id="tr.album_id" :has-cover="tr.has_cover" :version="tr.cover_v" rounded="rounded-md" class="size-11 flex-none" />
            <span class="flex min-w-0 flex-1 flex-col">
              <span class="truncate text-[15px]" :class="tr.id === video.track_id ? 'font-medium text-accent' : ''">{{ tr.title }}</span>
              <span class="truncate text-[13px] text-muted">{{ tr.artist || t('common.unknownArtist') }} · {{ tr.album || t('common.unknownAlbum') }}</span>
            </span>
          </button>
        </li>
      </ul>
      <ul v-if="tab === 'album' && albums?.length" class="flex flex-col" :class="busy ? 'opacity-60' : ''">
        <li v-for="a in albums" :key="a.id">
          <button
            type="button"
            class="flex w-full items-center gap-3 rounded-xl px-2 py-2 text-left hover:bg-surface"
            :class="a.id === video.album_id ? 'bg-accent-soft' : ''"
            :aria-current="a.id === video.album_id"
            @click="pickAlbum(a)"
          >
            <CoverArt :album-id="a.id" :has-cover="a.has_cover" :version="a.cover_v" rounded="rounded-md" class="size-11 flex-none" />
            <span class="flex min-w-0 flex-1 flex-col">
              <span class="truncate text-[15px]" :class="a.id === video.album_id ? 'font-medium text-accent' : ''">{{ a.title }}</span>
              <span class="truncate text-[13px] text-muted">{{ a.artist || t('common.unknownArtist') }}{{ a.year ? ` · ${a.year}` : '' }}</span>
            </span>
          </button>
        </li>
      </ul>
    </div>
  </BaseModal>
</template>
