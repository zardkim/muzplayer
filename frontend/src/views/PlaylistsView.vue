<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { BookHeadphones, Check, ChevronRight, ListMusic, ListVideo, Pencil, Plus, SquareCheckBig, Trash2, Zap } from '@lucide/vue'
import { api } from '../api'
import { appConfig } from '../config'
import BaseModal from '../components/BaseModal.vue'
import { errorMessage } from '../i18n'
import { useLibrary } from '../stores/library'
import { useUi } from '../stores/ui'
import PageHeader from '../components/PageHeader.vue'
import SmartRulesSheet from '../components/SmartRulesSheet.vue'
import BookGrid from '../components/BookGrid.vue'
import type { Book, Playlist, VideoPlaylist } from '../types'
import { youtubeThumb } from '../youtube'

const { t } = useI18n()
const library = useLibrary()
const ui = useUi()
const router = useRouter()
const route = useRoute()
const smartOpen = ref(false)
const smartEdit = ref<Playlist | undefined>() // a smart playlist whose rules are being changed

function smartSaved(p: Playlist) {
  const editing = !!smartEdit.value
  smartOpen.value = false
  smartEdit.value = undefined
  library.loadPlaylists().catch(() => {})
  if (!editing) router.push({ name: 'playlist', params: { id: p.id } })
}
// My playlists by what they hold: music, music videos, audiobooks (the books being listened to and
// the finished ones); the tab is in the address (?tab=video), so back comes to it
type Tab = 'music' | 'video' | 'books'
const tabs = computed<Tab[]>(() => (appConfig.audiobooks ? ['music', 'video', 'books'] : ['music', 'video']))
const tab = computed<Tab>({
  get: () => {
    // (My Music's "my video playlists" link: #video-playlists)
    const want = route.hash === '#video-playlists' ? 'video' : route.query.tab
    return tabs.value.includes(want as Tab) ? (want as Tab) : 'music'
  },
  set: (v) => void router.replace({ query: v === 'music' ? {} : { tab: v }, hash: '' }),
})
onMounted(() => {
  library.loadPlaylists().catch(() => {})
  library.loadVideoPlaylists().catch(() => {})
})
// my audiobooks, asked for when their tab opens
const books = ref<{ listening: Book[]; finished: Book[] } | null>(null)
watch(tab, (v) => {
  if (v === 'books' && !books.value) api<{ listening: Book[]; finished: Book[] }>('/books/mine').then((r) => (books.value = r), () => (books.value = { listening: [], finished: [] }))
}, { immediate: true })
// ---- the managing toolbar: new, smart (music), edit → change / delete the ticked ones ----
const TAB_ICONS = { music: ListMusic, video: ListVideo, books: BookHeadphones }
interface Item { id: number; name: string; smart: boolean; locked: boolean }
const items = computed<Item[]>(() =>
  tab.value === 'video'
    ? library.videoPlaylists.map((p) => ({ id: p.id, name: p.name, smart: false, locked: !!p.is_default }))
    : library.playlists.map((p) => ({ id: p.id, name: p.name, smart: p.kind === 'smart', locked: !!p.is_default })),
)
const editing = ref(false)
const ticked = ref(new Set<number>())
watch(tab, () => ((editing.value = false), (ticked.value = new Set())))
function tick(id: number) {
  const s = new Set(ticked.value)
  if (s.has(id)) s.delete(id)
  else s.add(id)
  ticked.value = s
}
const one = computed(() => (ticked.value.size === 1 ? items.value.find((x) => ticked.value.has(x.id)) ?? null : null))
const deletable = computed(() => items.value.filter((x) => ticked.value.has(x.id) && !x.locked))

// a name asked for: a new playlist, or the ticked one's
const naming = ref<{ mode: 'new' | 'rename'; id?: number } | null>(null)
const nameText = ref('')
function askName(mode: 'new' | 'rename') {
  naming.value = mode === 'new' ? { mode } : { mode, id: one.value!.id }
  nameText.value = mode === 'new' ? '' : one.value!.name
}
async function submitName() {
  const name = nameText.value.trim()
  const n = naming.value
  if (!name || !n) return
  const base = tab.value === 'video' ? '/video-playlists' : '/playlists'
  try {
    if (n.mode === 'new') {
      const p = tab.value === 'video'
        ? await api<VideoPlaylist>(base, { method: 'POST', body: { name } })
        : await library.createPlaylist(name)
      naming.value = null
      await reload()
      router.push({ name: tab.value === 'video' ? 'video-playlist' : 'playlist', params: { id: p.id } })
      return
    }
    await api(`${base}/${n.id}`, { method: 'PATCH', body: { name } })
    naming.value = null
    await reload()
  } catch (e) {
    ui.notify(errorMessage(e), true)
  }
}
// change: a smart playlist's rules, another's name
function change() {
  const x = one.value
  if (!x) return
  if (x.smart) {
    smartEdit.value = library.playlists.find((p) => p.id === x.id)
    smartOpen.value = true
  } else askName('rename')
}
async function removeTicked() {
  const gone = deletable.value
  if (!gone.length || !confirm(t('playlists.deleteManyConfirm', { n: gone.length, names: gone.map((x) => x.name).join(', ') }))) return
  const base = tab.value === 'video' ? '/video-playlists' : '/playlists'
  for (const x of gone) await api(`${base}/${x.id}`, { method: 'DELETE' }).catch((e) => ui.notify(errorMessage(e), true))
  ticked.value = new Set()
  editing.value = false
  await reload()
}
async function reload() {
  await (tab.value === 'video' ? library.loadVideoPlaylists() : library.loadPlaylists()).catch(() => {})
}
</script>

<template>
  <div class="flex flex-col gap-5">
    <PageHeader :title="t('playlists.title')">
      <!-- the kinds: on the title's line, as icons -->
      <template #actions>
        <div class="flex flex-none rounded-full bg-surface p-0.5 md:p-1" role="tablist" :aria-label="t('playlists.title')">
          <button
            v-for="k in tabs"
            :key="k"
            type="button"
            role="tab"
            :aria-selected="tab === k"
            :aria-label="t(`playlists.tab_${k}`)"
            :title="t(`playlists.tab_${k}`)"
            class="grid size-8 place-items-center rounded-full md:size-9"
            :class="tab === k ? 'bg-bg text-ink shadow-sm' : 'text-muted hover:text-ink'"
            @click="tab = k"
          >
            <component :is="TAB_ICONS[k]" :size="18" :stroke-width="tab === k ? 2 : 1.6" />
          </button>
        </div>
      </template>
    </PageHeader>

    <!-- the managing toolbar (music and video lists) -->
    <div v-if="tab !== 'books'" class="flex flex-wrap items-center gap-2 rounded-2xl bg-surface p-1.5">
      <template v-if="!editing">
        <button type="button" class="flex h-9 items-center gap-1.5 rounded-full bg-ink px-3.5 text-[14px] text-on-ink" @click="askName('new')">
          <Plus :size="16" :stroke-width="1.8" />{{ t('playlists.toolNew') }}
        </button>
        <button v-if="tab === 'music'" type="button" class="flex h-9 items-center gap-1.5 rounded-full px-3.5 text-[14px] hover:bg-bg" @click="(smartEdit = undefined), (smartOpen = true)">
          <Zap :size="16" :stroke-width="1.6" />{{ t('smart.new') }}
        </button>
        <span class="flex-1" />
        <span class="px-2 text-[13px] text-muted">{{ t(tab === 'music' ? 'playlists.countMusic' : 'playlists.countVideo', { n: items.length }) }}</span>
        <button type="button" class="flex h-9 items-center gap-1.5 rounded-full px-3.5 text-[14px] hover:bg-bg disabled:opacity-40" :disabled="!items.length" @click="editing = true">
          <SquareCheckBig :size="16" :stroke-width="1.6" />{{ t('playlists.toolEdit') }}
        </button>
      </template>
      <template v-else>
        <span class="px-2.5 text-[14px] font-medium">{{ t('playlists.ticked', { n: ticked.size }) }}</span>
        <button type="button" class="flex h-9 items-center gap-1.5 rounded-full px-3.5 text-[14px] hover:bg-bg disabled:opacity-40" :disabled="!one" @click="change">
          <Pencil :size="15" :stroke-width="1.6" />{{ one?.smart ? t('smart.edit') : t('common.rename') }}
        </button>
        <button type="button" class="flex h-9 items-center gap-1.5 rounded-full px-3.5 text-[14px] text-danger hover:bg-bg disabled:opacity-40" :disabled="!deletable.length" @click="removeTicked">
          <Trash2 :size="15" :stroke-width="1.6" />{{ deletable.length ? t('playlists.deleteN', { n: deletable.length }) : t('common.delete') }}
        </button>
        <span class="flex-1" />
        <button type="button" class="flex h-9 items-center gap-1.5 rounded-full bg-ink px-3.5 text-[14px] text-on-ink" @click="(editing = false), (ticked = new Set())">
          <Check :size="16" :stroke-width="1.8" />{{ t('playlists.toolDone') }}
        </button>
      </template>
    </div>
    <SmartRulesSheet v-if="smartOpen" :playlist="smartEdit" @close="(smartOpen = false), (smartEdit = undefined)" @saved="smartSaved" />
    <BaseModal v-if="naming" :title="naming.mode === 'new' ? t(tab === 'video' ? 'videos.newPlaylist' : 'playlists.new') : t('common.rename')" @close="naming = null">
      <form class="flex flex-col gap-4" @submit.prevent="submitName">
        <label class="flex flex-col gap-1.5 text-[13px] text-muted">
          {{ t('playlists.name') }}
          <input v-model="nameText" maxlength="200" autofocus class="h-12 rounded-full bg-surface px-4 text-base text-ink outline-none focus:ring-2 focus:ring-ink" />
        </label>
        <button type="submit" class="h-12 rounded-full bg-ink text-on-ink disabled:opacity-40" :disabled="!nameText.trim()">{{ naming.mode === 'new' ? t('common.create') : t('common.save') }}</button>
      </form>
    </BaseModal>

    <template v-if="tab === 'music'">
    <p v-if="!library.playlists.length" class="font-light text-muted">{{ t('playlists.empty') }}</p>
    <ul class="grid grid-cols-1 gap-x-8 sm:grid-cols-2 xl:grid-cols-3">
      <li v-for="p in library.playlists" :key="p.id">
        <component
          :is="editing ? 'label' : 'RouterLink'"
          :to="editing ? undefined : { name: 'playlist', params: { id: p.id } }"
          class="flex min-h-[72px] cursor-pointer items-center gap-3.5 border-b border-surface"
        >
          <input v-if="editing" type="checkbox" class="size-[18px] flex-none accent-ink" :checked="ticked.has(p.id)" @change="tick(p.id)" />
          <span class="grid size-[52px] flex-none place-items-center rounded-lg bg-surface"><Zap v-if="p.kind === 'smart'" :size="22" :stroke-width="1.3" /><ListMusic v-else :size="22" :stroke-width="1.3" /></span>
          <span class="flex min-w-0 flex-1 flex-col">
            <span class="truncate text-[17px]">{{ p.name }}</span>
            <span class="text-sm font-light text-muted">{{ p.kind === 'smart' ? t('smart.badge') : t('common.tracks', p.track_count ?? 0) }}{{ p.is_default ? ` · ${t('playlists.default')}` : '' }}</span>
          </span>
          <ChevronRight v-if="!editing" :size="18" class="text-subtle" />
        </component>
      </li>
    </ul>
    </template>

    <!-- video playlists -->
    <section v-if="tab === 'video'" id="video-playlists" class="flex flex-col gap-4">
      <p v-if="!library.videoPlaylists.length" class="font-light text-muted">{{ t('videos.noPlaylists') }}</p>
      <ul class="grid grid-cols-1 gap-x-8 sm:grid-cols-2 xl:grid-cols-3">
        <li v-for="p in library.videoPlaylists" :key="p.id">
          <component
            :is="editing ? 'label' : 'RouterLink'"
            :to="editing ? undefined : { name: 'video-playlist', params: { id: p.id } }"
            class="flex min-h-[72px] cursor-pointer items-center gap-3.5 border-b border-surface"
          >
            <input v-if="editing" type="checkbox" class="size-[18px] flex-none accent-ink" :checked="ticked.has(p.id)" @change="tick(p.id)" />
            <span class="relative grid aspect-video w-[84px] flex-none place-items-center overflow-hidden rounded-lg bg-surface">
              <img v-if="p.thumb" :src="youtubeThumb(p.thumb)" alt="" loading="lazy" class="absolute inset-0 h-full w-full object-cover" />
              <ListVideo v-else :size="22" :stroke-width="1.3" />
            </span>
            <span class="flex min-w-0 flex-1 flex-col">
              <span class="truncate text-[17px]">{{ p.name }}</span>
              <span class="text-sm font-light text-muted">{{ t('videos.count', { n: p.count }) }}{{ p.is_default ? ` · ${t('playlists.default')}` : '' }}</span>
            </span>
            <ChevronRight v-if="!editing" :size="18" class="text-subtle" />
          </component>
        </li>
      </ul>
    </section>

    <!-- my audiobooks: being listened to, finished -->
    <template v-if="tab === 'books'">
      <p v-if="!books" class="font-light text-muted">{{ t('common.loading') }}</p>
      <p v-else-if="!books.listening.length && !books.finished.length" class="font-light text-muted">{{ t('playlists.booksEmpty') }}</p>
      <template v-else>
        <section v-if="books.listening.length" class="flex flex-col gap-3.5">
          <h2 class="text-[20px] font-bold">{{ t('playlists.booksListening') }} <span class="text-[15px] font-normal text-muted">{{ books.listening.length }}</span></h2>
          <BookGrid :books="books.listening" />
        </section>
        <section v-if="books.finished.length" class="flex flex-col gap-3.5">
          <h2 class="text-[20px] font-bold">{{ t('playlists.booksFinished') }} <span class="text-[15px] font-normal text-muted">{{ books.finished.length }}</span></h2>
          <BookGrid :books="books.finished" />
        </section>
      </template>
    </template>
  </div>
</template>
