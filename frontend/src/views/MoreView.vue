<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Heart, History, LogOut, MicVocal, Music, Settings, Tag, Users } from '@lucide/vue'
import { useAuth } from '../stores/auth'
import { usePlayer } from '../stores/player'
import LanguageSwitch from '../components/LanguageSwitch.vue'

const { t } = useI18n()
const auth = useAuth()
const player = usePlayer()
const router = useRouter()
const links = [
  { to: '/tracks', label: 'nav.tracks', icon: Music },
  { to: '/artists', label: 'nav.artists', icon: MicVocal },
  { to: '/genres', label: 'nav.genres', icon: Tag },
  { to: '/favorites', label: 'nav.favorites', icon: Heart },
  { to: '/history', label: 'nav.history', icon: History },
  { to: '/settings', label: 'nav.settings', icon: Settings },
]

async function logout() {
  player.reset()
  await auth.logout()
  router.push({ name: 'login' })
}
</script>

<template>
  <div class="flex flex-col gap-6">
    <h1 class="text-[32px] font-bold tracking-tight">{{ t('nav.more') }}</h1>
    <nav class="flex flex-col">
      <RouterLink v-for="l in links" :key="l.to" :to="l.to" class="flex h-14 items-center gap-4 border-b border-surface-2 text-base">
        <component :is="l.icon" :size="22" class="text-muted" />{{ t(l.label) }}
      </RouterLink>
      <RouterLink v-if="auth.user?.is_admin" to="/admin" class="flex h-14 items-center gap-4 border-b border-surface-2 text-base">
        <Users :size="22" class="text-muted" />{{ t('nav.admin') }}
      </RouterLink>
      <button type="button" class="flex h-14 items-center gap-4 text-left text-base" @click="logout">
        <LogOut :size="22" class="text-muted" />{{ t('nav.logout') }}
      </button>
    </nav>
    <LanguageSwitch />
  </div>
</template>
