<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { ArrowDownUp, Check } from '@lucide/vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import { api, coverUrl } from '../api'
import type { Genre } from '../types'
import { useAuth } from '../stores/auth'
import LibraryHeader from '../components/LibraryHeader.vue'
import MergeSheet from '../components/MergeSheet.vue'
import PickBar from '../components/PickBar.vue'
import PickedMergeSheet from '../components/PickedMergeSheet.vue'
import { matches, useListSearch } from '../listSearch'
import { genreIcon } from '../genreIcons'
import { vLongPress } from '../longPress'
import SelectPill from '../components/SelectPill.vue'

// Genres as square tiles: the cover of the genre's biggest album, darkened, with a white picture of the genre
// (genreIcons.ts, by its name) and its name over it; a genre without covers gets a dark wash of its own colour.
const { t } = useI18n()
const auth = useAuth()
const merging = ref(false) // admin: the duplicates sheet
// admin: genres picked by hand to make one (tapping a tile picks it rather than opening it)
const picking = ref(false)
const picked = ref<Genre[]>([])
const choosing = ref(false) // the sheet choosing the name to keep
let pressedAt = 0
function pickOne(g: Genre) {
  if (Date.now() - pressedAt < 700) return // the tap that ended a long press
  picked.value = picked.value.some((p) => p.id === g.id) ? picked.value.filter((p) => p.id !== g.id) : [...picked.value, g]
}
const isPicked = (g: Genre) => picked.value.some((p) => p.id === g.id)
// a genre held down: picking starts (as the "pick" button), with it picked
function pressPick(g: Genre) {
  if (picking.value) pickOne(g)
  else {
    picking.value = true
    picked.value = [g]
  }
  pressedAt = Date.now()
}
function stopPicking() {
  picking.value = false
  picked.value = []
}
function afterMerge() {
  choosing.value = false
  stopPicking()
  void load()
}
const items = ref<Genre[]>([])
const loaded = ref(false)
// the order picked is in the address (?sort=name): back from a genre's songs comes to it again
const route = useRoute()
const router = useRouter()
const shownSort: 'size' | 'name' = route.query.sort === 'name' ? 'name' : 'size' // (another order is another page)
const sort = computed({
  get: () => shownSort,
  set: (v: 'size' | 'name') => void router.replace({ query: { ...route.query, sort: v === 'name' ? 'name' : undefined } }),
})
async function load() {
  items.value = (await api<{ items: Genre[] }>('/genres')).items
  loaded.value = true
}
onMounted(load)

const PALETTE = [
  '#E13300', '#1E3264', '#8D67AB', '#E8115B', '#148A08', '#BA5D07', '#503750', '#477D95',
  '#AF2896', '#509BF5', '#27856A', '#D84000', '#0D73EC', '#8C1932', '#777777', '#E91429',
  '#B49BC8', '#7358FF', '#F59B23', '#283EA8',
]
function hash(name: string) {
  let h = 0
  for (const ch of name) h = (h * 31 + ch.charCodeAt(0)) >>> 0
  return h
}
function colour(name: string) {
  return PALETTE[hash(name) % PALETTE.length]
}
// no cover: the genre's colour, deep, flowing into black (white text and icon on it)
function wash(name: string) {
  const c = colour(name)
  return { background: `linear-gradient(135deg, color-mix(in oklab, ${c} 75%, black) 0%, color-mix(in oklab, ${c} 30%, black) 100%)` }
}

const q = useListSearch()
const found = computed(() => items.value.filter((g) => matches(g.name, q.value)))
const sorted = computed(() =>
  sort.value === 'size'
    ? [...found.value].sort((a, b) => b.track_count - a.track_count || a.name.localeCompare(b.name))
    : found.value,
)
// a few screenfuls first, more as the end comes near (a library can have hundreds of genres, each
// tile with three covers: building them all at once, or while scrolling, makes a phone stutter)
const PAGE = 36
const count = ref(PAGE)
const shown = computed(() => sorted.value.slice(0, count.value))
watch([sort, q], () => (count.value = PAGE))
const more = ref<HTMLElement | null>(null)
let observer: IntersectionObserver | null = null
onMounted(() => {
  observer = new IntersectionObserver((entries) => {
    if (entries[0].isIntersecting && count.value < sorted.value.length) count.value += PAGE
  }, { rootMargin: '1200px 0px' })
  watch(more, (el, old) => {
    if (old) observer?.unobserve(old)
    if (el) observer?.observe(el)
  }, { immediate: true })
})
onUnmounted(() => observer?.disconnect())
</script>

<template>
  <div class="flex flex-col gap-6">
    <LibraryHeader v-model:search="q" :search-label="t('genres.search')" :sub="loaded && items.length ? t('genres.count', found.length) : undefined">
      <div class="flex items-center gap-1 text-[14px]">
        <button v-if="auth.user?.is_admin" type="button" class="pill-sm flex-none" :aria-pressed="picking" :class="picking ? 'border-ink bg-ink text-on-ink' : ''" @click="picking ? stopPicking() : (picking = true)">{{ t('merge.pick') }}</button>
        <button v-if="auth.user?.is_admin" type="button" class="pill-sm flex-none" @click="merging = true">{{ t('merge.open') }}</button>
        <SelectPill v-model="sort" :label="t('common.sort')" :icon="ArrowDownUp" :options="(['size', 'name'] as const).map((s) => ({ value: s, label: t(`genres.sort_${s}`) }))" />
      </div>
    </LibraryHeader>
    <p v-if="loaded && !items.length" class="font-light text-muted">{{ t('genres.empty') }}</p>
    <p v-else-if="loaded && !found.length" class="font-light text-muted">{{ t('search.noResults') }}</p>
    <MergeSheet v-if="merging" kind="genre" @close="merging = false" @changed="load" />
    <PickBar v-if="picking" :count="picked.length" @cancel="stopPicking" @merge="choosing = true" />
    <PickedMergeSheet v-if="choosing" kind="genre" :picked="picked.map((g) => ({ id: g.id, name: g.name, songs: g.track_count }))" @close="choosing = false" @merged="afterMerge" />

    <ul class="grid grid-cols-3 gap-2 sm:grid-cols-[repeat(auto-fill,minmax(160px,1fr))] sm:gap-3">
      <!-- off-screen tiles are neither drawn nor painted (content-visibility): smooth scrolling on phones -->
      <li v-for="g in shown" :key="g.id" class="[contain-intrinsic-size:auto_160px] [content-visibility:auto]">
        <component
          :is="picking ? 'button' : RouterLink"
          v-bind="picking ? { type: 'button', 'aria-pressed': isPicked(g) } : { to: { name: 'tracks', query: { genre: g.id } } }"
          class="group relative block aspect-square w-full select-none overflow-hidden rounded-lg [-webkit-touch-callout:none] text-white focus-visible:ring-2 focus-visible:ring-ink focus-visible:ring-offset-2"
          :class="picking && isPicked(g) ? 'ring-[3px] ring-accent ring-offset-2 ring-offset-bg' : ''"
          v-long-press="auth.user?.is_admin ? () => pressPick(g) : null"
          @click="picking && pickOne(g)"
          :style="g.covers?.length ? undefined : wash(g.name)"
        >
          <!-- the genre's biggest album, darkened under the picture -->
          <img
            v-if="g.covers?.length"
            :src="coverUrl(g.covers[0].id, 'thumb', g.covers[0].v)"
            alt=""
            loading="lazy"
            decoding="async"
            class="absolute inset-0 size-full object-cover transition-transform duration-500 group-hover:scale-105"
          />
          <span class="absolute inset-0 bg-black/60 transition-colors group-hover:bg-black/50" aria-hidden="true" />
          <span class="relative flex h-full flex-col items-center justify-center gap-1.5 px-2 text-center sm:gap-2">
            <component :is="genreIcon(g.name)" class="size-9 sm:size-12" :stroke-width="1.5" aria-hidden="true" />
            <span class="line-clamp-2 text-[13px] font-semibold leading-tight [text-wrap:balance] sm:text-[15px]">{{ g.name }}</span>
            <span class="text-[11px] text-white/70 sm:text-[12px]">{{ t('common.tracks', g.track_count) }}</span>
          </span>
          <span v-if="picking" class="absolute right-2 top-2 z-20 grid size-7 place-items-center rounded-full border-2" :class="isPicked(g) ? 'border-white bg-accent text-white' : 'border-white bg-black/25'"><Check v-if="isPicked(g)" :size="16" :stroke-width="2.5" /></span>
        </component>
      </li>
    </ul>
    <!-- once this comes within 1200px, the next tiles are added (a new one after each batch) -->
    <div v-if="shown.length < sorted.length" :key="shown.length" ref="more" class="h-px" aria-hidden="true" />
  </div>
</template>
