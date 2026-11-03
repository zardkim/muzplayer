<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, query } from '../api'
import { errorMessage } from '../i18n'
import { useUi } from '../stores/ui'
import type { Page, Track } from '../types'
import BaseModal from './BaseModal.vue'
import CoverArt from './CoverArt.vue'
import SearchField from './SearchField.vue'

// Linking a NAS video (ui.videoLink) to its song: a keyword (its title to begin with, without
// [MV], (Official Video) and the like), the library's songs that match, one picked.
const { t } = useI18n()
const ui = useUi()
const video = ui.videoLink!
const keyword = ref(
  video.title
    .replace(/[[(【（][^\])】）]*(?:m\/?v|official|video|lyric|4k|1080p|직캠|뮤비|teaser)[^\])】）]*[\])】）]/gi, ' ')
    .replace(/\b(?:official\s+(?:music\s+)?video|music\s+video|m\/?v|4k|1080p)\b/gi, ' ')
    .replace(/\s+/g, ' ')
    .trim(),
)
const results = ref<Track[] | null>(null)
const busy = ref(false)
const error = ref('')
let timer: number | undefined
let asked = 0

async function search() {
  const q = keyword.value.trim()
  if (!q) {
    results.value = null
    return
  }
  const mine = ++asked
  busy.value = true
  try {
    const r = await api<Page<Track>>(`/tracks${query({ q, limit: 30, sort: 'relevance' })}`)
    if (mine === asked) results.value = r.items
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
onMounted(search)
onUnmounted(() => clearTimeout(timer))

async function pick(track: Track) {
  try {
    await api(`/videos/${video.id}/link`, { method: 'POST', body: { track_id: track.id } })
    ui.notify(t('videos.linkedTo', { song: `${track.title} · ${track.artist}` }))
    ui.videoLinked++
    ui.videoLink = null
  } catch (e) {
    error.value = errorMessage(e)
  }
}
</script>

<template>
  <BaseModal wide :title="t('videos.linkTitle')" @close="ui.videoLink = null">
    <div class="flex flex-col gap-3">
      <p class="truncate text-[14px] text-muted">{{ video.title }}</p>
      <p class="text-[13px] text-muted">{{ t('videos.linkHint') }}</p>
      <SearchField v-model="keyword" large input-id="link-q" :placeholder="t('videos.linkSearch')" @submit="search" />
      <p v-if="error" class="text-[14px] text-danger" role="alert">{{ error }}</p>
      <p v-else-if="busy && !results" class="text-[14px] text-muted" role="status">{{ t('common.loading') }}</p>
      <p v-else-if="results && !results.length" class="text-[14px] text-muted">{{ t('videos.linkNone') }}</p>
      <ul v-if="results?.length" class="flex flex-col" :class="busy ? 'opacity-60' : ''">
        <li v-for="tr in results" :key="tr.id">
          <button
            type="button"
            class="flex w-full items-center gap-3 rounded-xl px-2 py-2 text-left hover:bg-surface"
            :class="tr.id === video.track_id ? 'bg-accent-soft' : ''"
            :aria-current="tr.id === video.track_id"
            @click="pick(tr)"
          >
            <CoverArt :album-id="tr.album_id" :has-cover="tr.has_cover" :version="tr.cover_v" rounded="rounded-md" class="size-11 flex-none" />
            <span class="flex min-w-0 flex-1 flex-col">
              <span class="truncate text-[15px]" :class="tr.id === video.track_id ? 'font-medium text-accent' : ''">{{ tr.title }}</span>
              <span class="truncate text-[13px] text-muted">{{ tr.artist || t('common.unknownArtist') }} · {{ tr.album || t('common.unknownAlbum') }}</span>
            </span>
          </button>
        </li>
      </ul>
    </div>
  </BaseModal>
</template>
