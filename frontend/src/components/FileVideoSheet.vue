<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { Trash2 } from '@lucide/vue'
import { api } from '../api'
import { errorMessage } from '../i18n'
import { usePlayer } from '../stores/player'
import { useUi } from '../stores/ui'
import { VIDEO_KINDS, type Video, type VideoKind } from '../types'
import BaseModal from './BaseModal.vue'

// A video file from the NAS (ui.fileVideo), played by the browser; who added it (or an admin) may
// change its kind or remove it.
const { t } = useI18n()
const ui = useUi()
const player = usePlayer()
const video = ref<Video>({ ...ui.fileVideo! })
const cantPlay = ref(false)
const pausedMusic = ref(false)

function playing() {
  if (player.playing) {
    player.toggle() // the song pauses while a video plays
    pausedMusic.value = true
  }
}

async function setKind(kind: VideoKind) {
  try {
    video.value = await api<Video>(`/videos/${video.value.id}`, { method: 'PATCH', body: { kind } })
  } catch (e) {
    ui.notify(errorMessage(e), true)
  }
}

async function remove() {
  if (!confirm(t('videos.removeConfirm', { title: video.value.title }))) return
  try {
    await api(`/videos/${video.value.id}`, { method: 'DELETE' })
    ui.fileVideo = null
  } catch (e) {
    ui.notify(errorMessage(e), true)
  }
}
</script>

<template>
  <BaseModal :title="video.title" @close="ui.fileVideo = null">
    <div class="flex flex-col gap-4">
      <div class="relative aspect-video overflow-hidden rounded-xl bg-black">
        <video :src="`/api/v1/videos/${video.id}/file`" controls autoplay playsinline class="absolute inset-0 h-full w-full" @play="playing" @error="cantPlay = true" />
        <p v-if="cantPlay" class="absolute inset-0 flex items-center justify-center bg-ink p-4 text-center text-[14px] text-on-ink">{{ t('videos.fileCantPlay') }}</p>
      </div>
      <p class="truncate text-[13px] text-muted">{{ t('videos.nas') }} · {{ video.file_path }}</p>
      <button v-if="pausedMusic" type="button" class="self-start text-[14px] text-accent underline" @click="player.toggle(), (pausedMusic = false)">{{ t('videos.resumeMusic') }}</button>

      <template v-if="video.can_edit">
        <div class="flex flex-wrap gap-1.5" role="radiogroup" :aria-label="t('videos.changeKind')">
          <button
            v-for="k in VIDEO_KINDS"
            :key="k"
            type="button"
            role="radio"
            :aria-checked="video.kind === k"
            class="h-9 rounded-full px-3.5 text-[14px]"
            :class="video.kind === k ? 'bg-ink text-on-ink' : 'bg-surface'"
            @click="setKind(k)"
          >{{ t(`videos.kinds.${k}`) }}</button>
        </div>
        <button type="button" class="flex h-10 items-center gap-1.5 self-start rounded-full border border-line-strong px-4 text-[14px] text-danger" @click="remove">
          <Trash2 :size="16" :stroke-width="1.5" />{{ t('videos.remove') }}
        </button>
      </template>
    </div>
  </BaseModal>
</template>
