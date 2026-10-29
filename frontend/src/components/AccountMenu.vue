<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { EllipsisVertical, LogOut, Settings, Users } from '@lucide/vue'
import { useAuth } from '../stores/auth'
import { usePlayer } from '../stores/player'
import LanguageSwitch from './LanguageSwitch.vue'

defineProps<{ avatar?: boolean }>()
const { t } = useI18n()
const auth = useAuth()
const player = usePlayer()
const router = useRouter()
const open = ref(false)

async function logout() {
  player.reset()
  await auth.logout()
  router.push({ name: 'login' })
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
      class="grid size-10 place-items-center rounded-full bg-ink text-[15px] font-medium text-white"
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
      <RouterLink to="/settings" class="flex items-center gap-3 px-4 py-3 hover:bg-surface" @click="open = false"><Settings :size="18" :stroke-width="1.4" />{{ t('nav.settings') }}</RouterLink>
      <RouterLink v-if="auth.user?.is_admin" to="/admin" class="flex items-center gap-3 px-4 py-3 hover:bg-surface" @click="open = false"><Users :size="18" :stroke-width="1.4" />{{ t('nav.admin') }}</RouterLink>
      <button type="button" class="flex items-center gap-3 px-4 py-3 text-left hover:bg-surface" @click="logout"><LogOut :size="18" :stroke-width="1.4" />{{ t('nav.logout') }}</button>
    </div>
  </div>
</template>
