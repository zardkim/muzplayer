<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { appConfig } from '../config'
import { errorMessage } from '../i18n'
import { useAuth } from '../stores/auth'
import AppLogo from '../components/AppLogo.vue'
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
// making an account here, when an admin turned sign-up on (open, or approved by an admin)
const joining = ref(false)
const displayName = ref('')
const waiting = ref(false) // signed up; an admin approves it first
function toggleJoin() {
  joining.value = !joining.value
  error.value = ''
  password.value = password2.value = ''
}

async function submit() {
  error.value = ''
  if ((setup.value || joining.value) && password.value !== password2.value) {
    error.value = t('login.mismatch')
    return
  }
  busy.value = true
  try {
    if (setup.value) {
      await auth.setup(username.value.trim(), password.value)
      appConfig.needsSetup = false
    } else if (joining.value) {
      if (await auth.signup(username.value.trim(), displayName.value.trim(), password.value)) {
        waiting.value = true
        joining.value = false
        password.value = password2.value = ''
        return
      }
    } else await auth.login(username.value, password.value)
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
  <div class="mx-auto flex min-h-dvh max-w-sm flex-col px-6 pb-[calc(2rem+env(safe-area-inset-bottom))] pt-[calc(env(safe-area-inset-top)+24px)]">
    <div class="-mr-3 flex justify-end"><LanguageMenu /></div>
    <div class="flex flex-1 flex-col justify-center gap-10">
      <div class="flex flex-col items-center gap-4">
        <AppLogo :size="88" :wordmark="false" />
        <h1 class="font-display text-4xl tracking-tight text-ink"><b>muz</b><span class="text-muted">player</span></h1>
      </div>
      <form class="flex flex-col gap-4" @submit.prevent="submit">
        <div v-if="joining" class="flex flex-col gap-1 text-center">
          <h2 class="text-lg font-bold">{{ t('login.joinTitle') }}</h2>
          <p class="text-[14px] font-light leading-relaxed text-muted">{{ appConfig.signup === 'approval' ? t('login.joinApproval') : t('login.joinOpen') }}</p>
        </div>
        <p v-if="waiting" role="status" class="rounded-2xl bg-accent-soft px-4 py-3 text-center text-[14px] leading-relaxed">{{ t('login.joinWaiting') }}</p>
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
            :pattern="setup || joining ? '[A-Za-z0-9._\\-]+' : undefined"
            :minlength="joining ? 3 : undefined"
            :maxlength="setup || joining ? 64 : undefined"
            class="field h-[52px] px-5"
          />
        </label>
        <label v-if="joining" class="flex flex-col gap-1.5 text-[13px] text-muted">
          {{ t('login.displayName') }}
          <input v-model="displayName" autocomplete="nickname" maxlength="100" class="field h-[52px] px-5" />
        </label>
        <label class="flex flex-col gap-1.5 text-[13px] text-muted">
          {{ t('login.password') }}
          <input
            v-model="password"
            type="password"
            :autocomplete="setup || joining ? 'new-password' : 'current-password'"
            required
            :minlength="setup || joining ? 8 : undefined"
            class="field h-[52px] px-5"
            :class="error ? 'ring-2 ring-danger' : ''"
          />
        </label>
        <label v-if="setup || joining" class="flex flex-col gap-1.5 text-[13px] text-muted">
          {{ t('login.passwordAgain') }}
          <input
            v-model="password2"
            type="password"
            autocomplete="new-password"
            required
            minlength="8"
            class="field h-[52px] px-5"
          />
        </label>
        <p v-if="error" role="alert" class="text-[13px] text-danger">{{ error }}</p>
        <button type="submit" :disabled="busy" class="mt-2 h-[52px] rounded-full bg-ink text-base text-on-ink disabled:opacity-60">
          {{ setup ? t('login.setupSubmit') : joining ? t('login.joinSubmit') : t('login.submit') }}
        </button>
        <button v-if="appConfig.signup !== 'off' && !setup" type="button" class="h-11 text-[15px] text-muted hover:text-ink" @click="toggleJoin">
          {{ joining ? t('login.haveAccount') : t('login.join') }}
        </button>
      </form>
    </div>
    <p v-if="!setup && appConfig.signup === 'off'" class="text-center text-[13px] font-light leading-relaxed text-muted">{{ t('login.help') }}<br />{{ t('login.help2') }}</p>
  </div>
</template>
