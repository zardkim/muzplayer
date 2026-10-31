<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ChevronRight, ListMusic, Plus, Sparkles, Zap } from '@lucide/vue'
import { appConfig } from '../config'
import { errorMessage } from '../i18n'
import { useLibrary } from '../stores/library'
import { useUi } from '../stores/ui'
import PageHeader from '../components/PageHeader.vue'
import AiPlaylistSheet, { type AiDraft } from '../components/AiPlaylistSheet.vue'
import SmartRulesSheet from '../components/SmartRulesSheet.vue'
import type { Playlist } from '../types'

const { t } = useI18n()
const library = useLibrary()
const ui = useUi()
const router = useRouter()
const name = ref('')
const smartOpen = ref(false)
const aiOpen = ref(false)
const draft = ref<AiDraft | undefined>()
function drafted(d: AiDraft) {
  aiOpen.value = false
  draft.value = d
  smartOpen.value = true
}

function smartSaved(p: Playlist) {
  smartOpen.value = false
  library.loadPlaylists().catch(() => {})
  router.push({ name: 'playlist', params: { id: p.id } })
}
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
      <button type="submit" class="flex h-11 items-center gap-1 rounded-full bg-ink px-4 text-[15px] text-on-ink disabled:opacity-40" :disabled="!name.trim()">
        <Plus :size="18" :stroke-width="1.6" />{{ t('common.create') }}
      </button>
    </form>
    <div class="flex flex-wrap gap-2">
      <button type="button" class="flex h-11 items-center gap-1.5 rounded-full border border-line-strong px-4 text-[15px]" @click="(draft = undefined), (smartOpen = true)">
        <Zap :size="17" :stroke-width="1.5" />{{ t('smart.new') }}
      </button>
      <button v-if="appConfig.aiPlaylists" type="button" class="flex h-11 items-center gap-1.5 rounded-full border border-line-strong px-4 text-[15px]" @click="aiOpen = true">
        <Sparkles :size="17" :stroke-width="1.5" />{{ t('ai.title') }}
      </button>
    </div>
    <AiPlaylistSheet v-if="aiOpen" @close="aiOpen = false" @draft="drafted" />
    <SmartRulesSheet v-if="smartOpen" :draft="draft" @close="smartOpen = false" @saved="smartSaved" />
    <p v-if="!library.playlists.length" class="font-light text-muted">{{ t('playlists.empty') }}</p>
    <ul class="grid grid-cols-1 gap-x-8 sm:grid-cols-2 xl:grid-cols-3">
      <li v-for="p in library.playlists" :key="p.id">
        <RouterLink :to="{ name: 'playlist', params: { id: p.id } }" class="flex min-h-[72px] items-center gap-3.5 border-b border-surface">
          <span class="grid size-[52px] flex-none place-items-center rounded-lg bg-surface"><Zap v-if="p.kind === 'smart'" :size="22" :stroke-width="1.3" /><ListMusic v-else :size="22" :stroke-width="1.3" /></span>
          <span class="flex min-w-0 flex-1 flex-col">
            <span class="truncate text-[17px]">{{ p.name }}</span>
            <span class="text-sm font-light text-muted">{{ p.kind === 'smart' ? t('smart.badge') : t('common.tracks', p.track_count ?? 0) }}</span>
          </span>
          <ChevronRight :size="18" class="text-subtle" />
        </RouterLink>
      </li>
    </ul>
  </div>
</template>
