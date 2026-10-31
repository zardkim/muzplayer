<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { EllipsisVertical, LogOut, MonitorSpeaker, Settings, UserPlus, Users } from '@lucide/vue'
import { useUi } from '../stores/ui'
import { errorMessage } from '../i18n'
import type { Account } from '../types'
import { useAuth } from '../stores/auth'
import { usePlayer } from '../stores/player'
import LanguageSwitch from './LanguageSwitch.vue'

defineProps<{ avatar?: boolean }>()
const { t } = useI18n()
const auth = useAuth()
const player = usePlayer()
const router = useRouter()
const ui = useUi()
const open = ref(false)

async function logout() {
  player.reset()
  await auth.logout() // restarts the app when another account on this device takes over
  router.push({ name: 'login' })
}

// user switching: the other accounts signed in on this device; an admin account asks for its password
watch(open, (o) => {
  if (o) void auth.loadAccounts()
  else (asking.value = null), (password.value = ''), (error.value = '')
})
const asking = ref<Account | null>(null)
const password = ref('')
const error = ref('')
async function switchTo(a: Account) {
  if (a.is_admin && asking.value?.id !== a.id) {
    asking.value = a
    return
  }
  error.value = ''
  try {
    player.saveProgress(true) // the audiobook position, while this account is still signed in
    await auth.switchTo(a.id, a.is_admin ? password.value : undefined) // reloads the app
  } catch (e) {
    error.value = errorMessage(e)
  }
}
function close(e: MouseEvent) {
  if (!(e.target as HTMLElement).closest('[data-account-menu]')) open.value = false
}
onMounted(() => document.addEventListener('click', close))
onUnmounted(() => document.removeEventListener('click', close))
</script>

<template>
  <div class="relative" data-account-menu>
    <button
      v-if="avatar"
      type="button"
      class="grid size-10 place-items-center rounded-full bg-ink text-[15px] font-medium text-on-ink"
      :aria-label="t('nav.accountMenu')"
      :aria-expanded="open"
      @click="open = !open"
    >
      {{ (auth.user?.display_name || '?').slice(0, 1).toUpperCase() }}
    </button>
    <button v-else type="button" class="grid size-11 place-items-center" :aria-label="t('nav.accountMenu')" :aria-expanded="open" @click="open = !open">
      <EllipsisVertical :size="24" :stroke-width="1.4" />
    </button>
    <div v-if="open" class="absolute right-0 top-12 z-40 flex w-64 flex-col overflow-hidden rounded-2xl border border-line bg-bg py-1.5 text-[15px] shadow-xl">
      <div class="border-b border-line px-4 pb-3 pt-2">
        <div class="font-semibold">{{ auth.user?.display_name }}</div>
        <div class="text-[13px] text-muted">{{ auth.user?.username }}</div>
        <LanguageSwitch compact class="mt-3" />
      </div>
      <template v-for="a in auth.accounts" :key="a.id">
        <button type="button" class="flex items-center gap-3 px-4 py-2.5 text-left hover:bg-surface" @click="switchTo(a)">
          <span class="grid size-7 flex-none place-items-center rounded-full bg-surface text-[13px] font-medium">{{ a.display_name.slice(0, 1).toUpperCase() }}</span>
          <span class="flex min-w-0 flex-col"><span class="truncate">{{ a.display_name }}</span><span class="text-[12px] text-muted">{{ t('account.switchTo') }}</span></span>
        </button>
        <form v-if="asking?.id === a.id" class="flex flex-col gap-2 px-4 pb-3" @submit.prevent="switchTo(a)">
          <input
            v-model="password"
            type="password"
            autocomplete="current-password"
            required
            :placeholder="t('account.adminPassword')"
            class="h-10 rounded-full bg-surface px-4 text-[14px] outline-none focus:ring-2 focus:ring-ink"
          />
          <p v-if="error" role="alert" class="text-[12px] text-danger">{{ error }}</p>
        </form>
      </template>
      <RouterLink :to="{ name: 'login', query: { add: '1' } }" class="flex items-center gap-3 border-b border-line px-4 py-3 hover:bg-surface" @click="open = false"><UserPlus :size="18" :stroke-width="1.4" />{{ t('account.add') }}</RouterLink>
      <button type="button" class="flex items-center gap-3 px-4 py-3 text-left hover:bg-surface" @click="(open = false), (ui.devicesOpen = true)"><MonitorSpeaker :size="18" :stroke-width="1.4" />{{ t('devices.title') }}</button>
      <RouterLink to="/settings" class="flex items-center gap-3 px-4 py-3 hover:bg-surface" @click="open = false"><Settings :size="18" :stroke-width="1.4" />{{ t('nav.settings') }}</RouterLink>
      <RouterLink v-if="auth.user?.is_admin" to="/admin" class="flex items-center gap-3 px-4 py-3 hover:bg-surface" @click="open = false"><Users :size="18" :stroke-width="1.4" />{{ t('nav.admin') }}</RouterLink>
      <button type="button" class="flex items-center gap-3 px-4 py-3 text-left hover:bg-surface" @click="logout"><LogOut :size="18" :stroke-width="1.4" />{{ t('nav.logout') }}</button>
    </div>
  </div>
</template>
