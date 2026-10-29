<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api'
import { errorMessage } from '../i18n'
import { useAuth } from '../stores/auth'
import { useUi } from '../stores/ui'
import LanguageSwitch from '../components/LanguageSwitch.vue'

const { t } = useI18n()
const auth = useAuth()
const ui = useUi()
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
const field = 'h-11 rounded-xl border border-line bg-surface px-3.5 text-base text-ink outline-none focus:border-accent'
</script>

<template>
  <div class="flex max-w-lg flex-col gap-10">
    <h1 class="text-[32px] font-bold tracking-tight">{{ t('settings.title') }}</h1>

    <section class="flex flex-col gap-3">
      <h2 class="text-lg font-bold">{{ t('settings.language') }}</h2>
      <LanguageSwitch />
    </section>

    <section class="flex flex-col gap-3">
      <h2 class="text-lg font-bold">{{ t('settings.account') }}</h2>
      <p class="text-sm text-muted">{{ auth.user?.display_name }} · {{ auth.user?.username }}</p>
      <form class="flex flex-col gap-3" @submit.prevent="changePassword">
        <h3 class="mt-2 font-semibold">{{ t('settings.changePassword') }}</h3>
        <label class="flex flex-col gap-1.5 text-[13px] text-muted">{{ t('settings.currentPassword') }}<input v-model="current" type="password" autocomplete="current-password" required :class="field" /></label>
        <label class="flex flex-col gap-1.5 text-[13px] text-muted">{{ t('settings.newPassword') }}<input v-model="next" type="password" autocomplete="new-password" minlength="8" required :class="field" /></label>
        <label class="flex flex-col gap-1.5 text-[13px] text-muted">{{ t('settings.confirmPassword') }}<input v-model="confirmNext" type="password" autocomplete="new-password" minlength="8" required :class="field" /></label>
        <p v-if="error" role="alert" class="text-[13px] text-danger">{{ error }}</p>
        <button type="submit" class="h-11 self-start rounded-full bg-accent px-6 font-semibold text-bg">{{ t('common.save') }}</button>
      </form>
    </section>

    <p v-if="version" class="font-display text-xs text-subtle">{{ t('settings.version', { v: version }) }}</p>
  </div>
</template>
