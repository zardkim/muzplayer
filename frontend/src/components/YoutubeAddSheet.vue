<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api'
import { errorMessage } from '../i18n'
import { useUi } from '../stores/ui'
import { VIDEO_KINDS, type VideoKind, type VideoListItem } from '../types'
import BaseModal from './BaseModal.vue'
import YoutubeIcon from './YoutubeIcon.vue'

// The Music videos page: a YouTube video by its link, on its own (no album page or song menu to
// start from). Its song is found from its title when that says which; else ⋮ → pick the song.
const { t } = useI18n()
const ui = useUi()
const emit = defineEmits<{ close: []; added: [] }>()
const link = ref('')
const kind = ref<VideoKind>('mv')
const busy = ref(false)
const error = ref('')

async function add() {
  busy.value = true
  error.value = ''
  try {
    const v = await api<VideoListItem>('/videos', { method: 'POST', body: { video: link.value.trim(), kind: kind.value } })
    let linked: 'track' | 'album' | null = null
    try {
      linked = (await api<VideoListItem>(`/videos/${v.id}/link`, { method: 'POST', body: { auto: true } })).target?.type ?? null
    } catch {
      /* no song or album fits its title: it stays on its own (an admin links it by hand) */
    }
    ui.notify(linked === 'album' ? t('videos.addedLinkedAlbum') : linked ? t('videos.addedLinked') : t('videos.added'))
    emit('added')
    emit('close')
  } catch (e) {
    error.value = errorMessage(e)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <BaseModal :title="t('videos.addYoutube')" @close="emit('close')">
    <form class="flex flex-col gap-4" @submit.prevent="add">
      <p class="text-[14px] leading-relaxed text-muted">{{ t('videos.addYoutubeHint') }}</p>
      <label class="flex h-12 items-center gap-2.5 rounded-full bg-surface px-4 focus-within:ring-2 focus-within:ring-ink">
        <YoutubeIcon :size="20" />
        <input v-model="link" type="url" inputmode="url" required minlength="11" :placeholder="t('videos.pastePlaceholder')" class="min-w-0 flex-1 bg-transparent text-base outline-none" :aria-label="t('videos.paste')" />
      </label>
      <div class="flex flex-wrap items-center gap-1.5" role="radiogroup" :aria-label="t('videos.kind')">
        <button
          v-for="k in VIDEO_KINDS"
          :key="k"
          type="button"
          role="radio"
          :aria-checked="kind === k"
          class="h-9 rounded-full px-3.5 text-[14px]"
          :class="kind === k ? 'bg-ink text-on-ink' : 'bg-surface'"
          @click="kind = k"
        >{{ t(`videos.kinds.${k}`) }}</button>
      </div>
      <p v-if="error" role="alert" class="text-[13px] text-danger">{{ error }}</p>
      <button type="submit" class="h-11 self-end rounded-full bg-ink px-6 text-[15px] text-on-ink disabled:opacity-50" :disabled="busy || !link.trim()">{{ t('videos.register') }}</button>
    </form>
  </BaseModal>
</template>
