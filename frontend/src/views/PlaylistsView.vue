<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Heart, History, ListMusic, Plus } from '@lucide/vue'
import { errorMessage } from '../i18n'
import { useLibrary } from '../stores/library'
import { useUi } from '../stores/ui'

const { t } = useI18n()
const library = useLibrary()
const ui = useUi()
const router = useRouter()
const name = ref('')
onMounted(() => library.loadPlaylists().catch(() => {}))

async function create() {
  if (!name.value.trim()) return
  try {
    const p = await library.createPlaylist(name.value.trim())
    router.push({ name: 'playlist', params: { id: p.id } })
  } catch (e) {
    ui.notify(errorMessage(e), true)
  }
}
</script>

<template>
  <div class="flex flex-col gap-6">
    <h1 class="text-[32px] font-bold tracking-tight">{{ t('playlists.title') }}</h1>

    <!-- favorites and history live in the library tab on phones -->
    <div class="grid grid-cols-2 gap-3 md:hidden">
      <RouterLink to="/favorites" class="flex h-14 items-center gap-3 rounded-xl bg-surface-2 px-4 font-semibold"><Heart :size="20" class="text-accent" />{{ t('nav.favorites') }}</RouterLink>
      <RouterLink to="/history" class="flex h-14 items-center gap-3 rounded-xl bg-surface-2 px-4 font-semibold"><History :size="20" class="text-accent" />{{ t('nav.history') }}</RouterLink>
    </div>

    <form class="flex max-w-md gap-2" @submit.prevent="create">
      <label for="pl-name" class="sr-only">{{ t('playlists.name') }}</label>
      <input id="pl-name" v-model="name" maxlength="200" :placeholder="t('playlists.new')" class="h-11 min-w-0 flex-1 rounded-xl border border-line bg-surface px-3.5 text-base outline-none focus:border-accent" />
      <button type="submit" class="flex h-11 items-center gap-1.5 rounded-full bg-surface-2 px-4 text-sm disabled:opacity-40" :disabled="!name.trim()">
        <Plus :size="18" />{{ t('common.create') }}
      </button>
    </form>

    <p v-if="!library.playlists.length" class="text-muted">{{ t('playlists.empty') }}</p>
    <ul class="grid grid-cols-1 gap-x-6 sm:grid-cols-2 xl:grid-cols-3">
      <li v-for="p in library.playlists" :key="p.id">
        <RouterLink :to="{ name: 'playlist', params: { id: p.id } }" class="flex min-h-[64px] items-center gap-3.5 rounded-xl px-2 hover:bg-surface">
          <span class="grid size-[52px] flex-none place-items-center rounded-[10px] bg-surface-2 text-accent"><ListMusic :size="22" /></span>
          <span class="flex min-w-0 flex-col">
            <span class="truncate text-[15px] font-semibold">{{ p.name }}</span>
            <span class="text-[13px] text-muted">{{ t('common.tracks', p.track_count) }}</span>
          </span>
        </RouterLink>
      </li>
    </ul>
  </div>
</template>
