<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ArrowDownUp, Check, ChevronRight } from '@lucide/vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { api, query } from '../api'
import { useProgressive } from '../progressive'
import type { Artist, Page, ViewMode } from '../types'
import { useAuth } from '../stores/auth'
import ArtistPhoto from '../components/ArtistPhoto.vue'
import LibraryHeader from '../components/LibraryHeader.vue'
import MergeSheet from '../components/MergeSheet.vue'
import PickBar from '../components/PickBar.vue'
import PickedMergeSheet from '../components/PickedMergeSheet.vue'
import ViewToggle from '../components/ViewToggle.vue'
import LoadMore from '../components/LoadMore.vue'
import SelectPill from '../components/SelectPill.vue'
import { useUi } from '../stores/ui'
import { aliasHit, useListSearch } from '../listSearch'

const { t } = useI18n()
const auth = useAuth()
const merging = ref(false) // admin: the duplicates sheet
// admin: artists picked by hand to make one (tapping a name picks it rather than opening it)
const picking = ref(false)
const picked = ref<Artist[]>([])
const choosing = ref(false) // the sheet choosing the name to keep
function pickOne(a: Artist) {
  picked.value = picked.value.some((p) => p.id === a.id) ? picked.value.filter((p) => p.id !== a.id) : [...picked.value, a]
}
const isPicked = (a: Artist) => picked.value.some((p) => p.id === a.id)
function stopPicking() {
  picking.value = false
  picked.value = []
}
function afterMerge() {
  choosing.value = false
  stopPicking()
  reload()
}
const ui = useUi()
const view = computed(() => (ui.views.artists as ViewMode) || 'grid')
const items = ref<Artist[]>([])
const total = ref(0)
const loading = ref(false)
const shown = useProgressive(() => items.value)

const q = useListSearch(() => reload())
let asked = 0
// 가나다 by the Korean name when there is one (머라이어 캐리 under ㅁ), or by the name shown; and an index letter
const sort = computed({
  get: () => (ui.views.artistSort === 'own' ? 'own' : 'ko'),
  set: (v: 'ko' | 'own') => {
    ui.views = { ...ui.views, artistSort: v }
    if (initial) pickInitial(initial)
    else reload()
  },
})
// the index letter picked is in the address (?initial=ㄷ): back from an artist comes to the same
// letter, even when the list was made again meanwhile; another letter is another page (kept apart)
const route = useRoute()
const router = useRouter()
const initial = typeof route.query.initial === 'string' ? route.query.initial : ''
const initials = ref<string[]>([])
function pickInitial(letter: string) {
  void router.replace({ query: { ...route.query, initial: initial === letter ? undefined : letter } })
}

async function load() {
  const mine = ++asked
  loading.value = true
  try {
    const page = await api<Page<Artist> & { initials: string[] }>(
      `/artists${query({ q: q.value.trim() || undefined, sort: sort.value, initial: initial || undefined, limit: 200, offset: items.value.length })}`,
    )
    if (mine !== asked) return
    items.value.push(...page.items)
    total.value = page.total
    initials.value = page.initials
  } finally {
    if (mine === asked) loading.value = false
  }
}
onMounted(load)
function reload() {
  items.value = []
  void load()
}
</script>

<template>
  <div class="flex flex-col gap-5">
    <LibraryHeader v-model:search="q" :search-label="t('artists.search')" :sub="t('artists.count', total)">
      <div class="flex items-center gap-2">
        <button v-if="auth.user?.is_admin" type="button" class="h-8 flex-none rounded-full border border-line-strong px-3 text-[13px] hover:border-ink" :aria-pressed="picking" :class="picking ? 'border-ink bg-ink text-on-ink' : ''" @click="picking ? stopPicking() : (picking = true)">{{ t('merge.pick') }}</button>
        <button v-if="auth.user?.is_admin" type="button" class="h-8 flex-none rounded-full border border-line-strong px-3 text-[13px] hover:border-ink" @click="merging = true">{{ t('merge.open') }}</button>
        <ViewToggle page="artists" fallback="grid" />
      </div>
    </LibraryHeader>
    <div class="-mt-2 flex flex-col gap-3">
      <SelectPill v-model="sort" class="self-start" :label="t('common.sort')" :icon="ArrowDownUp" :options="[{ value: 'ko', label: t('artists.sortKo') }, { value: 'own', label: t('artists.sortOwn') }]" />
      <!-- index letters that have artists: one picked shows those alone -->
      <nav v-if="initials.length > 1" :aria-label="t('artists.index')" class="-mx-5 flex gap-1 overflow-x-auto px-5 [scrollbar-width:none] md:mx-0 md:flex-wrap md:px-0">
        <button
          v-for="l in initials"
          :key="l"
          type="button"
          class="h-8 min-w-8 flex-none rounded-full px-2 text-[14px]"
          :class="initial === l ? 'bg-ink text-on-ink' : 'bg-surface hover:bg-surface-2'"
          :aria-pressed="initial === l"
          @click="pickInitial(l)"
        >{{ l === 'etc' ? t('artists.indexEtc') : l }}</button>
      </nav>
    </div>
    <PickBar v-if="picking" :count="picked.length" @cancel="stopPicking" @merge="choosing = true" />
    <p v-if="!loading && !items.length && q.trim()" class="font-light text-muted">{{ t('search.noResults') }}</p>
    <ul
      v-if="view !== 'list'"
      class="grid gap-x-4 gap-y-6"
      :class="view === 'grid' ? 'grid-cols-3 sm:grid-cols-[repeat(auto-fill,minmax(130px,1fr))]' : 'grid-cols-2 sm:grid-cols-[repeat(auto-fill,minmax(200px,1fr))] sm:gap-x-6'"
    >
      <li v-for="a in shown" :key="a.id">
        <component
          :is="picking ? 'button' : RouterLink"
          v-bind="picking ? { type: 'button', 'aria-pressed': isPicked(a) } : { to: { name: 'artist', params: { id: a.id } } }"
          class="group relative flex w-full flex-col items-center gap-2.5 text-center"
          @click="picking && pickOne(a)"
        >
          <ArtistPhoto :artist-id="a.id" :name="a.name" :version="a.image_v" :size="view === 'cover' ? 'large' : 'thumb'" class="w-full transition-transform duration-200 group-hover:scale-[1.03]" :class="picking && isPicked(a) ? 'ring-[3px] ring-accent ring-offset-2 ring-offset-bg' : ''" />
          <span v-if="picking" class="absolute left-0 top-0 grid size-7 place-items-center rounded-full border-2" :class="isPicked(a) ? 'border-accent bg-accent text-white' : 'border-white bg-black/30'"><Check v-if="isPicked(a)" :size="16" :stroke-width="2.5" /></span>
          <span class="flex w-full min-w-0 flex-col">
            <span class="truncate" :class="view === 'cover' ? 'text-[17px] font-medium' : 'text-[15px]'">{{ a.name }}</span>
            <span class="truncate text-[13px] font-light text-muted">{{ aliasHit(a, q) ?? t('common.tracks', a.track_count) }}</span>
          </span>
        </component>
      </li>
    </ul>
    <ul v-else class="grid grid-cols-1 gap-x-8 sm:grid-cols-2 xl:grid-cols-3">
      <li v-for="a in shown" :key="a.id">
        <component
          :is="picking ? 'button' : RouterLink"
          v-bind="picking ? { type: 'button', 'aria-pressed': isPicked(a) } : { to: { name: 'artist', params: { id: a.id } } }"
          class="flex min-h-[64px] w-full items-center gap-3.5 border-b border-surface text-left"
          @click="picking && pickOne(a)"
        >
          <span v-if="picking" class="grid size-6 flex-none place-items-center rounded-full border-2" :class="isPicked(a) ? 'border-accent bg-accent text-white' : 'border-line-strong'"><Check v-if="isPicked(a)" :size="14" :stroke-width="2.5" /></span>
          <ArtistPhoto :artist-id="a.id" :name="a.name" :version="a.image_v" class="size-11 flex-none" />
          <span class="flex min-w-0 flex-1 flex-col">
            <span class="truncate text-[17px]">{{ a.name }}</span>
            <span class="text-sm font-light text-muted"><template v-if="aliasHit(a, q)">{{ aliasHit(a, q) }} · </template><template v-if="a.album_count">{{ t('common.albums', a.album_count) }} · </template>{{ t('common.tracks', a.track_count) }}</span>
          </span>
          <ChevronRight v-if="!picking" :size="18" class="text-subtle" />
        </component>
      </li>
    </ul>
    <MergeSheet v-if="merging" kind="artist" @close="merging = false" @changed="reload" />
    <PickedMergeSheet v-if="choosing" kind="artist" :picked="picked.map((a) => ({ id: a.id, name: a.name, songs: a.track_count }))" @close="choosing = false" @merged="afterMerge" />
    <LoadMore v-if="items.length < total" auto :loading="loading" @click="load" />
  </div>
</template>
