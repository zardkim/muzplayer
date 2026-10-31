<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { Sparkles } from '@lucide/vue'
import { api } from '../api'
import { errorMessage } from '../i18n'
import type { SmartRules } from '../types'
import BaseModal from './BaseModal.vue'

// A smart playlist from a sentence: the server asks the AI for rules over this library's own genres
// and artists (backend ai_playlist.py); the result opens in the rules sheet to check and save.
export interface AiDraft {
  name: string
  rules: SmartRules
  count: number
}
const emit = defineEmits<{ close: []; draft: [draft: AiDraft] }>()
const { t } = useI18n()
const prompt = ref('')
const busy = ref(false)
const error = ref('')
const examples = [t('ai.example1'), t('ai.example2'), t('ai.example3')]

async function submit() {
  if (prompt.value.trim().length < 2) return
  busy.value = true
  error.value = ''
  try {
    emit('draft', await api<AiDraft>('/playlists/ai', { method: 'POST', body: { prompt: prompt.value.trim() } }))
  } catch (e) {
    error.value = errorMessage(e)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <BaseModal :title="t('ai.title')" @close="emit('close')">
    <form class="flex flex-col gap-4" @submit.prevent="submit">
      <p class="text-[14px] font-light text-muted">{{ t('ai.intro') }}</p>
      <textarea
        v-model="prompt"
        rows="3"
        maxlength="300"
        :placeholder="examples[0]"
        class="resize-none rounded-2xl bg-surface px-4 py-3 text-base text-ink outline-none focus:ring-2 focus:ring-ink"
      />
      <div class="flex flex-wrap gap-2">
        <button v-for="ex in examples" :key="ex" type="button" class="rounded-full border border-line-strong px-3 py-1.5 text-[13px]" @click="prompt = ex">{{ ex }}</button>
      </div>
      <p v-if="error" role="alert" class="text-[13px] text-danger">{{ error }}</p>
      <button type="submit" class="flex h-12 items-center justify-center gap-2 rounded-full bg-ink text-on-ink disabled:opacity-40" :disabled="busy || prompt.trim().length < 2">
        <span v-if="busy" class="size-4 animate-spin rounded-full border-2 border-on-ink/40 border-t-on-ink" />
        <Sparkles v-else :size="18" :stroke-width="1.5" />
        {{ busy ? t('ai.thinking') : t('ai.make') }}
      </button>
    </form>
  </BaseModal>
</template>
