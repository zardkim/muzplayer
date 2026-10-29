<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api'
import { appConfig } from '../config'
import { errorMessage } from '../i18n'
import { install, installPrompt, isIos, isStandalone } from '../pwa'
import { useAuth } from '../stores/auth'
import { SKIPS, usePlayer } from '../stores/player'
import { useUi } from '../stores/ui'
import LanguageSwitch from '../components/LanguageSwitch.vue'
import PageHeader from '../components/PageHeader.vue'

const { t } = useI18n()
const auth = useAuth()
const ui = useUi()
const player = usePlayer()
const version = (window as unknown as { __MUZ_VERSION__?: string }).__MUZ_VERSION__ ?? ''
const current = ref('')
const next = ref('')
const confirmNext = ref('')
const error = ref('')

async function changePassword() {
  error.value = ''
  if (next.value !== confirmNext.value) {
    error.value = t('settings.mismatch')
    return
  }
  try {
    await api('/auth/password', { method: 'PUT', body: { current_password: current.value, new_password: next.value } })
    current.value = next.value = confirmNext.value = ''
    ui.notify(t('settings.changed'))
  } catch (e) {
    error.value = errorMessage(e)
  }
}
const field = 'h-12 rounded-full bg-surface px-4 text-base text-ink outline-none focus:ring-2 focus:ring-ink'
</script>

<template>
  <div class="flex max-w-lg flex-col gap-9">
    <PageHeader :title="t('settings.title')" />

    <section class="flex flex-col gap-3">
      <h2 class="text-lg font-bold">{{ t('settings.language') }}</h2>
      <LanguageSwitch />
    </section>

    <section v-if="appConfig.audiobooks" class="flex flex-col gap-3">
      <h2 class="text-lg font-bold">{{ t('settings.audiobooks') }}</h2>
      <div class="flex flex-wrap gap-4">
        <label class="flex items-center gap-2.5 text-[15px]">
          {{ t('settings.skipBack') }}
          <select v-model.number="player.skipBack" class="h-10 rounded-full border border-line-strong bg-bg px-3 text-sm">
            <option v-for="s in SKIPS" :key="s" :value="s">{{ t('settings.seconds', { n: s }) }}</option>
          </select>
        </label>
        <label class="flex items-center gap-2.5 text-[15px]">
          {{ t('settings.skipForward') }}
          <select v-model.number="player.skipForward" class="h-10 rounded-full border border-line-strong bg-bg px-3 text-sm">
            <option v-for="s in SKIPS" :key="s" :value="s">{{ t('settings.seconds', { n: s }) }}</option>
          </select>
        </label>
      </div>
      <p class="text-[13px] font-light text-muted">{{ t('settings.audiobooksHelp') }}</p>
    </section>

    <section class="flex flex-col gap-3">
      <h2 class="text-lg font-bold">{{ t('settings.installTitle') }}</h2>
      <p v-if="isStandalone" class="font-light text-muted">{{ t('settings.installed') }}</p>
      <button v-else-if="installPrompt" type="button" class="h-11 self-start rounded-full bg-ink px-5 text-[15px] text-white" @click="install">{{ t('settings.installApp') }}</button>
      <p v-else-if="isIos" class="font-light text-muted">{{ t('settings.installIos') }}</p>
    </section>

    <section class="flex flex-col gap-3">
      <h2 class="text-lg font-bold">{{ t('settings.account') }}</h2>
      <p class="font-light text-muted">{{ auth.user?.display_name }} · {{ auth.user?.username }}</p>
      <form class="flex flex-col gap-3" @submit.prevent="changePassword">
        <h3 class="mt-2 font-medium">{{ t('settings.changePassword') }}</h3>
        <label class="flex flex-col gap-1.5 text-[13px] text-muted">{{ t('settings.currentPassword') }}<input v-model="current" type="password" autocomplete="current-password" required :class="field" /></label>
        <label class="flex flex-col gap-1.5 text-[13px] text-muted">{{ t('settings.newPassword') }}<input v-model="next" type="password" autocomplete="new-password" minlength="8" required :class="field" /></label>
        <label class="flex flex-col gap-1.5 text-[13px] text-muted">{{ t('settings.confirmPassword') }}<input v-model="confirmNext" type="password" autocomplete="new-password" minlength="8" required :class="field" /></label>
        <p v-if="error" role="alert" class="text-[13px] text-danger">{{ error }}</p>
        <button type="submit" class="h-11 self-start rounded-full bg-ink px-6 text-[15px] text-white">{{ t('common.save') }}</button>
      </form>
    </section>

    <p v-if="version" class="font-display text-xs text-muted">{{ t('settings.version', { v: version }) }}</p>
  </div>
</template>
