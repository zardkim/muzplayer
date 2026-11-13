<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api'
import { errorMessage } from '../i18n'
import { useUi } from '../stores/ui'
import type { Lyrics } from '../types'
import BaseModal from './BaseModal.vue'
import { useAuth } from '../stores/auth'
import { useLyrics } from '../stores/lyrics'

// A song's lyrics from a list (ui.lyricsTarget), without playing it: the synced lines as text.
// The song that is playing shows them in the player instead, in time.
const { t } = useI18n()
const ui = useUi()
const target = ui.lyricsTarget!
const auth = useAuth()
const { fresh } = useLyrics()
function manage() {
  ui.lyricsAdmin = { ...target }
  ui.lyricsTarget = null
}
const lyrics = ref<Lyrics | null>(null)
const error = ref('')

onMounted(async () => {
  try {
    lyrics.value = await api<Lyrics>(`/tracks/${target.trackId}/lyrics${fresh.has(target.trackId) ? `?v=${fresh.get(target.trackId)}` : ''}`)
  } catch (e) {
    error.value = errorMessage(e)
  }
})
</script>

<template>
  <BaseModal :title="t('lyricsSheet.title', { title: target.title })" @close="ui.lyricsTarget = null">
    <p class="-mt-2 mb-4 truncate text-[14px] font-light text-muted">{{ target.artist }}</p>
    <p v-if="error" class="text-[15px] text-danger" role="alert">{{ error }}</p>
    <p v-else-if="!lyrics" class="text-[15px] text-muted" role="status">{{ t('common.loading') }}</p>
    <template v-else-if="lyrics.synced?.length">
      <p class="mb-3 text-[12px] font-medium text-muted">{{ t('lyricsSheet.synced') }}</p>
      <ol class="flex flex-col gap-2 text-[17px] leading-snug">
        <li v-for="([sec, line], i) in lyrics.synced" :key="i" class="flex gap-3">
          <span class="w-11 flex-none pt-0.5 font-display text-[12px] text-subtle">{{ Math.floor(sec / 60) }}:{{ String(Math.floor(sec % 60)).padStart(2, '0') }}</span>
          <span :class="line ? '' : 'h-3'">{{ line }}</span>
        </li>
      </ol>
    </template>
    <p v-else-if="lyrics.plain" class="whitespace-pre-line text-[17px] leading-relaxed">{{ lyrics.plain }}</p>
    <p v-else class="text-[15px] text-muted">{{ t('lyricsSheet.none') }}</p>
    <button v-if="auth.user?.is_admin" type="button" class="mt-6 h-10 rounded-full border border-line-strong px-4 text-[14px] hover:border-ink" @click="manage">{{ t('lyricsAdmin.open') }}</button>
  </BaseModal>
</template>
