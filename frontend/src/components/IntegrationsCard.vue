<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api'
import { appConfig } from '../config'
import { errorMessage } from '../i18n'
import { useUi } from '../stores/ui'

// AI banner and YouTube keys, set by an admin and kept on the server (conf/settings.json).
// The page never gets a key back, only whether one is set; an empty box leaves it as it is.
defineProps<{ counts?: { banners: number; without_banner: number } | null }>()
const { t } = useI18n()
const ui = useUi()

type Secret = 'gemini_api_key' | 'openai_api_key' | 'youtube_api_key'
interface Integrations {
  ai_provider: 'gemini' | 'openai'
  gemini_image_model: string
  openai_image_model: string
  default_models: Record<'gemini' | 'openai', string>
  gemini_api_key_set: boolean
  openai_api_key_set: boolean
  youtube_api_key_set: boolean
  ai_banners: boolean
  youtube_search: boolean
}

const state = ref<Integrations | null>(null)
const provider = ref<'gemini' | 'openai'>('gemini')
const model = ref('')
const keys = ref<Record<Secret, string>>({ gemini_api_key: '', openai_api_key: '', youtube_api_key: '' })
const busy = ref(false)

const aiKey = computed<Secret>(() => (provider.value === 'openai' ? 'openai_api_key' : 'gemini_api_key'))

function apply(s: Integrations) {
  state.value = s
  provider.value = s.ai_provider
  model.value = s[`${s.ai_provider}_image_model`]
  keys.value = { gemini_api_key: '', openai_api_key: '', youtube_api_key: '' }
  appConfig.aiBanners = s.ai_banners
  appConfig.youtubeSearch = s.youtube_search
}

onMounted(() => {
  api<Integrations>('/admin/integrations').then(apply, (e) => ui.notify(errorMessage(e), true))
})

function switchProvider(p: 'gemini' | 'openai') {
  provider.value = p
  model.value = state.value?.[`${p}_image_model`] ?? ''
}

async function save(body: Record<string, string>) {
  busy.value = true
  try {
    apply(await api<Integrations>('/admin/integrations', { method: 'PUT', body }))
    ui.notify(t('common.saved'))
  } catch (e) {
    ui.notify(errorMessage(e), true)
  } finally {
    busy.value = false
  }
}

function saveAi() {
  const body: Record<string, string> = { ai_provider: provider.value, [`${provider.value}_image_model`]: model.value.trim() }
  if (keys.value[aiKey.value].trim()) body[aiKey.value] = keys.value[aiKey.value].trim()
  save(body)
}

function saveYoutube() {
  if (keys.value.youtube_api_key.trim()) save({ youtube_api_key: keys.value.youtube_api_key.trim() })
}

function clear(key: Secret) {
  if (confirm(t('admin.keyClearConfirm'))) save({ [key]: '' })
}

const field = 'h-12 min-w-0 rounded-full bg-surface px-4 text-base text-ink outline-none focus:ring-2 focus:ring-ink'
</script>

<template>
  <section v-if="state" class="flex flex-col gap-6 rounded-2xl border border-line p-5 md:p-6">
    <div>
      <h2 class="text-xl font-bold">{{ t('admin.keysTitle') }}</h2>
      <p class="mt-1 text-sm font-light text-muted">{{ t('admin.keysDesc') }}</p>
    </div>

    <form class="flex flex-col gap-3" @submit.prevent="saveAi">
      <h3 class="flex items-center gap-2 text-[17px] font-medium">
        {{ t('admin.aiTitle') }}
        <span class="text-[13px] font-normal" :class="state.ai_banners ? 'text-ink' : 'text-muted'">· {{ state.ai_banners ? t('admin.aiOn') : t('admin.aiOff') }}</span>
      </h3>
      <p class="text-[13px] font-light text-muted">{{ t('admin.aiDesc') }}</p>
      <p v-if="counts" class="text-[13px] text-muted">{{ t('admin.aiCounts', { banners: counts.banners, without: counts.without_banner }) }}</p>
      <label class="flex flex-col gap-1.5 text-[13px] text-muted">
        {{ t('admin.aiProvider') }}
        <select :value="provider" :class="field" @change="switchProvider(($event.target as HTMLSelectElement).value as 'gemini' | 'openai')">
          <option value="gemini">Google Gemini</option>
          <option value="openai">OpenAI</option>
        </select>
      </label>
      <label class="flex flex-col gap-1.5 text-[13px] text-muted">
        {{ t('admin.apiKey') }}
        <input
          v-model="keys[aiKey]"
          type="password"
          autocomplete="off"
          maxlength="500"
          :placeholder="state[`${aiKey}_set`] ? t('admin.keySaved') : t('admin.keyEmpty')"
          :class="field"
        />
      </label>
      <label class="flex flex-col gap-1.5 text-[13px] text-muted">
        {{ t('admin.aiModel') }}
        <input v-model="model" maxlength="100" autocapitalize="none" :placeholder="state.default_models[provider]" :class="field" />
      </label>
      <div class="flex flex-wrap items-center gap-3">
        <button type="submit" class="h-10 rounded-full bg-ink px-5 text-[15px] text-white disabled:opacity-40" :disabled="busy">{{ t('common.save') }}</button>
        <button v-if="state[`${aiKey}_set`]" type="button" class="text-[14px] text-muted underline" :disabled="busy" @click="clear(aiKey)">{{ t('admin.keyClear') }}</button>
      </div>
    </form>

    <form class="flex flex-col gap-3 border-t border-surface pt-5" @submit.prevent="saveYoutube">
      <h3 class="flex items-center gap-2 text-[17px] font-medium">
        {{ t('admin.ytTitle') }}
        <span class="text-[13px] font-normal" :class="state.youtube_search ? 'text-ink' : 'text-muted'">· {{ state.youtube_search ? t('admin.aiOn') : t('admin.aiOff') }}</span>
      </h3>
      <p class="text-[13px] font-light leading-relaxed text-muted">{{ t('admin.ytHelp') }}</p>
      <label class="flex flex-col gap-1.5 text-[13px] text-muted">
        {{ t('admin.apiKey') }}
        <input
          v-model="keys.youtube_api_key"
          type="password"
          autocomplete="off"
          maxlength="500"
          :placeholder="state.youtube_api_key_set ? t('admin.keySaved') : t('admin.keyEmpty')"
          :class="field"
        />
      </label>
      <div class="flex flex-wrap items-center gap-3">
        <button type="submit" class="h-10 rounded-full bg-ink px-5 text-[15px] text-white disabled:opacity-40" :disabled="busy || !keys.youtube_api_key.trim()">{{ t('common.save') }}</button>
        <button v-if="state.youtube_api_key_set" type="button" class="text-[14px] text-muted underline" :disabled="busy" @click="clear('youtube_api_key')">{{ t('admin.keyClear') }}</button>
      </div>
    </form>
  </section>
</template>
