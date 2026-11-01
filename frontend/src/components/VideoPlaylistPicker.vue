<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ListVideo, Plus } from '@lucide/vue'
import { youtubeThumb } from '../youtube'
import { api } from '../api'
import { errorMessage } from '../i18n'
import { useLibrary } from '../stores/library'
import { useUi } from '../stores/ui'
import type { VideoPlaylist } from '../types'
import BaseModal from './BaseModal.vue'

// Putting videos (ui.videoPick) in one of this person's video playlists, or in a new one.
const { t } = useI18n()
const ui = useUi()
const library = useLibrary()
const videos = ui.videoPick!
const lists = ref<VideoPlaylist[] | null>(null)
const name = ref('')
const error = ref('')

onMounted(async () => {
  try {
    lists.value = (await api<{ items: VideoPlaylist[] }>('/video-playlists')).items
  } catch (e) {
    error.value = errorMessage(e)
  }
})

async function addTo(id: number, listName: string) {
  try {
    const r = await api<{ added: number; skipped: number }>(`/video-playlists/${id}/videos`, { method: 'POST', body: { video_ids: videos.map((v) => v.id) } })
    ui.notify(r.added ? t('videos.addedTo', { name: listName }) : t('videos.alreadyThere', { name: listName }))
    ui.videoPick = null
    library.loadVideoPlaylists().catch(() => {}) // counts, pictures, a new list: the sidebar and pages
  } catch (e) {
    error.value = errorMessage(e)
  }
}

async function create() {
  if (!name.value.trim()) return
  try {
    const p = await api<VideoPlaylist>('/video-playlists', { method: 'POST', body: { name: name.value.trim() } })
    await addTo(p.id, p.name)
  } catch (e) {
    error.value = errorMessage(e)
  }
}
</script>

<template>
  <BaseModal :title="t('videos.addToPlaylist')" @close="ui.videoPick = null">
    <div class="flex flex-col gap-3">
      <form class="flex gap-2" @submit.prevent="create">
        <label for="vp-new" class="sr-only">{{ t('videos.newPlaylist') }}</label>
        <input id="vp-new" v-model="name" maxlength="200" :placeholder="t('videos.newPlaylist')" class="h-11 min-w-0 flex-1 rounded-full bg-surface px-4 text-[15px] outline-none focus:ring-2 focus:ring-ink" />
        <button type="submit" class="flex h-11 flex-none items-center gap-1 rounded-full bg-ink px-4 text-[15px] text-on-ink disabled:opacity-40" :disabled="!name.trim()">
          <Plus :size="17" :stroke-width="1.6" />{{ t('common.create') }}
        </button>
      </form>
      <p v-if="error" class="text-[14px] text-danger" role="alert">{{ error }}</p>
      <p v-else-if="!lists" class="text-[14px] text-muted">{{ t('common.loading') }}</p>
      <template v-else>
      <h3 class="mt-1 text-[13px] font-medium text-muted">{{ t('videos.myVideoPlaylists') }}</h3>
      <p v-if="!lists.length" class="text-[14px] leading-relaxed text-muted">{{ t('videos.pickerEmpty') }}</p>
      <ul class="flex flex-col">
        <li v-for="p in lists" :key="p.id">
          <button type="button" class="flex w-full items-center gap-3 rounded-xl px-2 py-2.5 text-left hover:bg-surface" @click="addTo(p.id, p.name)">
            <span class="relative grid aspect-video w-16 flex-none place-items-center overflow-hidden rounded-lg bg-surface">
              <img v-if="p.thumb" :src="youtubeThumb(p.thumb)" alt="" loading="lazy" class="absolute inset-0 h-full w-full object-cover" />
              <ListVideo v-else :size="19" :stroke-width="1.4" />
            </span>
            <span class="flex min-w-0 flex-col">
              <span class="truncate text-[15px]">{{ p.name }}</span>
              <span class="text-[12px] text-muted">{{ t('videos.count', { n: p.count }) }}</span>
            </span>
          </button>
        </li>
      </ul>
      </template>
    </div>
  </BaseModal>
</template>
