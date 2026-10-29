<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { errorMessage } from '../i18n'
import { useAuth } from '../stores/auth'
import LanguageSwitch from '../components/LanguageSwitch.vue'

const { t } = useI18n()
const auth = useAuth()
const route = useRoute()
const router = useRouter()
const username = ref('')
const password = ref('')
const error = ref('')
const busy = ref(false)

async function submit() {
  error.value = ''
  busy.value = true
  try {
    await auth.login(username.value, password.value)
    const next = typeof route.query.next === 'string' && route.query.next.startsWith('/') ? route.query.next : '/'
    router.replace(next)
  } catch (e) {
    error.value = errorMessage(e)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="pb-safe mx-auto flex min-h-dvh max-w-sm flex-col px-6 pb-8 pt-6">
    <div class="flex justify-end"><LanguageSwitch compact /></div>
    <div class="flex flex-1 flex-col justify-center gap-10">
      <div class="flex flex-col items-center gap-4">
        <img src="/logo.svg" alt="" width="88" height="88" />
        <h1 class="font-display text-4xl tracking-tight"><b>muz</b><span class="text-muted">player</span></h1>
      </div>
      <form class="flex flex-col gap-4" @submit.prevent="submit">
        <label class="flex flex-col gap-1.5 text-[13px] text-muted">
          {{ t('login.username') }}
          <input
            v-model="username"
            autocomplete="username"
            autocapitalize="none"
            required
            class="h-[52px] rounded-xl border border-line bg-surface px-4 text-base text-ink outline-none focus:border-accent"
          />
        </label>
        <label class="flex flex-col gap-1.5 text-[13px] text-muted">
          {{ t('login.password') }}
          <input
            v-model="password"
            type="password"
            autocomplete="current-password"
            required
            class="h-[52px] rounded-xl border bg-surface px-4 text-base text-ink outline-none focus:border-accent"
            :class="error ? 'border-danger' : 'border-line'"
          />
        </label>
        <p v-if="error" role="alert" class="text-[13px] text-danger">{{ error }}</p>
        <button type="submit" :disabled="busy" class="mt-2 h-[52px] rounded-full bg-accent text-base font-semibold text-bg disabled:opacity-60">
          {{ t('login.submit') }}
        </button>
      </form>
    </div>
    <p class="text-center text-[13px] leading-relaxed text-muted">{{ t('login.help') }}<br />{{ t('login.help2') }}</p>
  </div>
</template>
