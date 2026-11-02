<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { EllipsisVertical, LogOut, Settings, UserPlus, Users } from '@lucide/vue'
import { errorMessage } from '../i18n'
import type { Account } from '../types'
import { useAuth } from '../stores/auth'
import { usePlayer } from '../stores/player'
import LanguageSwitch from './LanguageSwitch.vue'

// where it sits: the PC sidebar's foot (a row with the person's name) or the phone's tab bar (a tab);
// the menu opens above it, laid over the page (the bars around it would cut it off)
const props = defineProps<{ variant: 'sidebar' | 'tab'; collapsed?: boolean }>()
const { t } = useI18n()
const auth = useAuth()
const player = usePlayer()
const router = useRouter()
const open = ref(false)
const trigger = ref<HTMLElement | null>(null)
const spot = ref<{ left: number; bottom: number }>({ left: 0, bottom: 0 })
const initial = computed(() => (auth.user?.display_name || '?').slice(0, 1).toUpperCase())
async function toggle() {
  open.value = !open.value
  if (!open.value) return
  await nextTick()
  const r = trigger.value!.getBoundingClientRect()
  const width = 256
  spot.value = {
    left: Math.max(8, Math.min(window.innerWidth - width - 8, props.variant === 'tab' ? r.right - width : r.left)),
    bottom: window.innerHeight - r.top + 8,
  }
}

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
      v-if="variant === 'sidebar'"
      ref="trigger"
      type="button"
      class="flex h-11 w-full items-center gap-3 rounded-full text-left text-[15px] hover:bg-surface"
      :class="collapsed ? 'justify-center' : 'px-1.5'"
      :aria-label="t('nav.accountMenu')"
      :title="collapsed ? auth.user?.display_name : undefined"
      :aria-expanded="open"
      @click="toggle"
    >
      <span class="grid size-8 flex-none place-items-center rounded-full bg-ink text-[14px] font-medium text-on-ink">{{ initial }}</span>
      <template v-if="!collapsed">
        <span class="min-w-0 flex-1 truncate">{{ auth.user?.display_name }}</span>
        <EllipsisVertical :size="18" :stroke-width="1.4" class="mr-1.5 flex-none text-muted" />
      </template>
    </button>
    <button
      v-else
      ref="trigger"
      type="button"
      class="flex h-[60px] min-w-[68px] flex-col items-center justify-center gap-[3px] rounded-full px-1 text-[11px]"
      :class="open ? 'bg-surface-2 font-medium' : ''"
      :aria-label="t('nav.accountMenu')"
      :aria-expanded="open"
      @click="toggle"
    >
      <span class="grid size-6 place-items-center rounded-full bg-ink text-[12px] font-medium text-on-ink">{{ initial }}</span>{{ t('nav.account') }}
    </button>
    <Teleport to="body">
    <div v-if="open" data-account-menu class="fixed z-[80] flex max-h-[80vh] w-64 flex-col overflow-y-auto rounded-2xl border border-line bg-bg py-1.5 text-[15px] shadow-xl" :style="{ left: `${spot.left}px`, bottom: `${spot.bottom}px` }">
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
      <RouterLink to="/settings" class="flex items-center gap-3 px-4 py-3 hover:bg-surface" @click="open = false"><Settings :size="18" :stroke-width="1.4" />{{ t('nav.settings') }}</RouterLink>
      <RouterLink v-if="auth.user?.is_admin" to="/admin" class="flex items-center gap-3 px-4 py-3 hover:bg-surface" @click="open = false"><Users :size="18" :stroke-width="1.4" />{{ t('nav.admin') }}</RouterLink>
      <button type="button" class="flex items-center gap-3 px-4 py-3 text-left hover:bg-surface" @click="logout"><LogOut :size="18" :stroke-width="1.4" />{{ t('nav.logout') }}</button>
    </div>
    </Teleport>
  </div>
</template>
