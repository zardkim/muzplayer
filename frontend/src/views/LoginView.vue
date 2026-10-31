<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { appConfig } from '../config'
import { errorMessage } from '../i18n'
import { useAuth } from '../stores/auth'
import LanguageMenu from '../components/LanguageMenu.vue'

const { t } = useI18n()
const auth = useAuth()
const route = useRoute()
const router = useRouter()
const username = ref('')
const password = ref('')
const password2 = ref('')
// a fresh install: this page makes the first account, which is the admin
const setup = ref(appConfig.needsSetup)
const error = ref('')
const busy = ref(false)
// adding another account on this device: the one signed in now stays (account menu → switch)
const adding = !!route.query.add && !!auth.user

async function submit() {
  error.value = ''
  if (setup.value && password.value !== password2.value) {
    error.value = t('login.mismatch')
    return
  }
  busy.value = true
  try {
    if (setup.value) {
      await auth.setup(username.value.trim(), password.value)
      appConfig.needsSetup = false
    } else await auth.login(username.value, password.value, adding)
    if (adding) {
      window.location.assign('/') // start afresh as the new account
      return
    }
    const next = typeof route.query.next === 'string' && route.query.next.startsWith('/') ? route.query.next : '/'
    router.replace(next)
  } catch (e) {
    error.value = errorMessage(e)
    if (setup.value && (e as { code?: string }).code === 'already_set_up') setup.value = false // someone was first
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="pb-safe mx-auto flex min-h-dvh max-w-sm flex-col px-6 pb-8 pt-[calc(env(safe-area-inset-top)+24px)]">
    <div class="-mr-3 flex justify-end"><LanguageMenu /></div>
    <div class="flex flex-1 flex-col justify-center gap-10">
      <div class="flex flex-col items-center gap-4">
        <img src="/logo.svg" alt="" width="88" height="88" />
        <h1 class="font-display text-4xl tracking-tight text-ink"><b>muz</b><span class="text-muted">player</span></h1>
      </div>
      <form class="flex flex-col gap-4" @submit.prevent="submit">
        <div v-if="adding" class="flex flex-col gap-1 text-center">
          <h2 class="text-lg font-bold">{{ t('login.addTitle') }}</h2>
          <p class="text-[14px] font-light leading-relaxed text-muted">{{ t('login.addDesc', { name: auth.user?.display_name }) }}</p>
        </div>
        <div v-if="setup" class="flex flex-col gap-1 text-center">
          <h2 class="text-lg font-bold">{{ t('login.setupTitle') }}</h2>
          <p class="text-[14px] font-light leading-relaxed text-muted">{{ t('login.setupDesc') }}</p>
        </div>
        <label class="flex flex-col gap-1.5 text-[13px] text-muted">
          {{ t('login.username') }}
          <input
            v-model="username"
            autocomplete="username"
            autocapitalize="none"
            required
            :pattern="setup ? '[A-Za-z0-9._\\-]+' : undefined"
            :maxlength="setup ? 64 : undefined"
            class="h-[52px] rounded-full bg-surface px-5 text-base text-ink outline-none focus:ring-2 focus:ring-ink"
          />
        </label>
        <label class="flex flex-col gap-1.5 text-[13px] text-muted">
          {{ t('login.password') }}
          <input
            v-model="password"
            type="password"
            :autocomplete="setup ? 'new-password' : 'current-password'"
            required
            :minlength="setup ? 8 : undefined"
            class="h-[52px] rounded-full bg-surface px-5 text-base text-ink outline-none focus:ring-2 focus:ring-ink"
            :class="error ? 'ring-2 ring-danger' : ''"
          />
        </label>
        <label v-if="setup" class="flex flex-col gap-1.5 text-[13px] text-muted">
          {{ t('login.passwordAgain') }}
          <input
            v-model="password2"
            type="password"
            autocomplete="new-password"
            required
            minlength="8"
            class="h-[52px] rounded-full bg-surface px-5 text-base text-ink outline-none focus:ring-2 focus:ring-ink"
          />
        </label>
        <p v-if="error" role="alert" class="text-[13px] text-danger">{{ error }}</p>
        <button type="submit" :disabled="busy" class="mt-2 h-[52px] rounded-full bg-ink text-base text-on-ink disabled:opacity-60">
          {{ setup ? t('login.setupSubmit') : t('login.submit') }}
        </button>
        <button v-if="adding" type="button" class="h-11 text-[15px] text-muted" @click="router.back()">{{ t('common.cancel') }}</button>
      </form>
    </div>
    <p v-if="!setup" class="text-center text-[13px] font-light leading-relaxed text-muted">{{ t('login.help') }}<br />{{ t('login.help2') }}</p>
  </div>
</template>
