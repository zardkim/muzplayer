<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ChevronRight, ListMusic, Plus } from '@lucide/vue'
import { errorMessage } from '../i18n'
import { useLibrary } from '../stores/library'
import { useUi } from '../stores/ui'
import PageHeader from '../components/PageHeader.vue'

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
    <PageHeader :title="t('playlists.title')" />
    <form class="flex max-w-md gap-2" @submit.prevent="create">
      <label for="pl-name" class="sr-only">{{ t('playlists.name') }}</label>
      <input id="pl-name" v-model="name" maxlength="200" :placeholder="t('playlists.new')" class="h-11 min-w-0 flex-1 rounded-full bg-surface px-4 text-base outline-none focus:ring-2 focus:ring-ink" />
      <button type="submit" class="flex h-11 items-center gap-1 rounded-full bg-ink px-4 text-[15px] text-white disabled:opacity-40" :disabled="!name.trim()">
        <Plus :size="18" :stroke-width="1.6" />{{ t('common.create') }}
      </button>
    </form>
    <p v-if="!library.playlists.length" class="font-light text-muted">{{ t('playlists.empty') }}</p>
    <ul class="grid grid-cols-1 gap-x-8 sm:grid-cols-2 xl:grid-cols-3">
      <li v-for="p in library.playlists" :key="p.id">
        <RouterLink :to="{ name: 'playlist', params: { id: p.id } }" class="flex min-h-[72px] items-center gap-3.5 border-b border-surface">
          <span class="grid size-[52px] flex-none place-items-center rounded-lg bg-surface"><ListMusic :size="22" :stroke-width="1.3" /></span>
          <span class="flex min-w-0 flex-1 flex-col">
            <span class="truncate text-[17px]">{{ p.name }}</span>
            <span class="text-sm font-light text-muted">{{ t('common.tracks', p.track_count) }}</span>
          </span>
          <ChevronRight :size="18" class="text-subtle" />
        </RouterLink>
      </li>
    </ul>
  </div>
</template>
