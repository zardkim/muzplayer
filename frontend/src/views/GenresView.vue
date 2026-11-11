<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { ArrowDownUp, Check } from '@lucide/vue'
import { RouterLink } from 'vue-router'
import { api, coverUrl } from '../api'
import type { Genre } from '../types'
import { useAuth } from '../stores/auth'
import LibraryHeader from '../components/LibraryHeader.vue'
import MergeSheet from '../components/MergeSheet.vue'
import PickBar from '../components/PickBar.vue'
import PickedMergeSheet from '../components/PickedMergeSheet.vue'
import { matches, useListSearch } from '../listSearch'
import SelectPill from '../components/SelectPill.vue'

// Genres as pastel tiles: each genre keeps its own colour (from its name), washed see-through, with the covers of
// its biggest albums fanned out in the corner. The largest genres get wide tiles up top.
const { t } = useI18n()
const auth = useAuth()
const merging = ref(false) // admin: the duplicates sheet
// admin: genres picked by hand to make one (tapping a tile picks it rather than opening it)
const picking = ref(false)
const picked = ref<Genre[]>([])
const choosing = ref(false) // the sheet choosing the name to keep
function pickOne(g: Genre) {
  picked.value = picked.value.some((p) => p.id === g.id) ? picked.value.filter((p) => p.id !== g.id) : [...picked.value, g]
}
const isPicked = (g: Genre) => picked.value.some((p) => p.id === g.id)
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
const sort = ref<'size' | 'name'>('size')
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
// a see-through pastel of the genre's colour flowing into a second one (picked by the name too),
// with a soft glow in the top corner; dark text on it (light and dark themes alike)
function tint(name: string) {
  const c = colour(name)
  const vivid = PALETTE.filter((x) => x !== '#777777' && x !== c) // (grey would dull it)
  const c2 = vivid[(hash(name) >>> 3) % vivid.length]
  const mix = (col: string, n: number) => `color-mix(in oklab, ${col} ${n}%, transparent)`
  return {
    background: [
      `radial-gradient(110% 85% at 0% 0%, ${mix(c, 50)} 0%, transparent 65%)`,
      `linear-gradient(in oklch 135deg, ${mix(c, 32)} 0%, ${mix(c2, 30)} 100%)`,
    ].join(', '),
    borderColor: mix(c, 35),
  }
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
// wide tiles for the four biggest genres (only when sorted by size and there are enough)
const wide = computed(() => (sort.value === 'size' && !q.value.trim() && items.value.length >= 8 ? 4 : 0))
// fanned covers: back to front
const FAN = ['rotate-[-14deg] translate-x-[-58%]', 'rotate-[-2deg] translate-x-[-28%]', 'rotate-[16deg]']
const FAN_HOVER = ['group-hover:rotate-[-20deg] group-hover:translate-x-[-72%]', 'group-hover:rotate-[-4deg] group-hover:translate-x-[-34%]', 'group-hover:rotate-[22deg] group-hover:translate-x-[6%]']
</script>

<template>
  <div class="flex flex-col gap-6">
    <LibraryHeader v-model:search="q" :search-label="t('genres.search')" :sub="loaded && items.length ? t('genres.count', found.length) : undefined">
      <div class="flex items-center gap-1 text-[14px]">
        <button v-if="auth.user?.is_admin" type="button" class="h-8 flex-none rounded-full border border-line-strong px-3 text-[13px] hover:border-ink" :aria-pressed="picking" :class="picking ? 'border-ink bg-ink text-on-ink' : ''" @click="picking ? stopPicking() : (picking = true)">{{ t('merge.pick') }}</button>
        <button v-if="auth.user?.is_admin" type="button" class="h-8 flex-none rounded-full border border-line-strong px-3 text-[13px] hover:border-ink" @click="merging = true">{{ t('merge.open') }}</button>
        <SelectPill v-model="sort" :label="t('common.sort')" :icon="ArrowDownUp" :options="(['size', 'name'] as const).map((s) => ({ value: s, label: t(`genres.sort_${s}`) }))" />
      </div>
    </LibraryHeader>
    <p v-if="loaded && !items.length" class="font-light text-muted">{{ t('genres.empty') }}</p>
    <p v-else-if="loaded && !found.length" class="font-light text-muted">{{ t('search.noResults') }}</p>
    <MergeSheet v-if="merging" kind="genre" @close="merging = false" @changed="load" />
    <PickBar v-if="picking" :count="picked.length" @cancel="stopPicking" @merge="choosing = true" />
    <PickedMergeSheet v-if="choosing" kind="genre" :picked="picked.map((g) => ({ id: g.id, name: g.name, songs: g.track_count }))" @close="choosing = false" @merged="afterMerge" />

    <ul class="grid grid-flow-dense grid-cols-2 gap-3 sm:grid-cols-[repeat(auto-fill,minmax(200px,1fr))] sm:gap-4">
      <!-- off-screen tiles are neither drawn nor painted (content-visibility): smooth scrolling on phones -->
      <li v-for="(g, i) in shown" :key="g.id" class="[contain-intrinsic-size:auto_150px] [content-visibility:auto]" :class="i < wide ? 'col-span-2' : ''">
        <component
          :is="picking ? 'button' : RouterLink"
          v-bind="picking ? { type: 'button', 'aria-pressed': isPicked(g) } : { to: { name: 'tracks', query: { genre: g.id } } }"
          class="group relative block w-full overflow-hidden rounded-2xl border text-left text-ink shadow-sm transition-transform duration-200 hover:-translate-y-0.5 hover:shadow-lg focus-visible:ring-2 focus-visible:ring-ink focus-visible:ring-offset-2"
          :class="[i < wide ? 'aspect-[2.1/1]' : 'aspect-[1.35/1]', picking && isPicked(g) ? 'ring-[3px] ring-accent ring-offset-2 ring-offset-bg' : '']"
          @click="picking && pickOne(g)"
          :style="tint(g.name)"
        >
          <span class="relative z-10 flex flex-col p-4" :class="i < wide ? 'md:p-5' : ''">
            <span class="font-bold leading-tight [text-wrap:balance]" :class="i < wide ? 'text-[26px] md:text-[30px]' : 'text-[20px]'">{{ g.name }}</span>
            <span class="mt-1 text-[13px] font-medium text-muted">{{ t('common.tracks', g.track_count) }}</span>
          </span>
          <!-- the genre's biggest albums, fanned out in the corner -->
          <span v-if="g.covers?.length" class="absolute bottom-[-12%] right-[-6%] h-[62%] w-[42%]" aria-hidden="true">
            <img
              v-for="(c, k) in g.covers.slice(0, 3)"
              :key="c.id"
              :src="coverUrl(c.id, 'thumb', c.v)"
              alt=""
              loading="lazy"
              decoding="async"
              class="absolute bottom-0 right-0 aspect-square h-full rounded-lg object-cover shadow-[0_3px_8px_rgba(0,0,0,0.3)] transition-transform duration-300 ease-out"
              :class="[FAN[k + 3 - Math.min(3, g.covers.length)], FAN_HOVER[k + 3 - Math.min(3, g.covers.length)]]"
            />
          </span>
          <span v-else class="absolute bottom-3 right-4 text-[64px] font-black leading-none text-ink/10" aria-hidden="true">#</span>
          <span v-if="picking" class="absolute right-2.5 top-2.5 z-20 grid size-7 place-items-center rounded-full border-2" :class="isPicked(g) ? 'border-white bg-accent text-white' : 'border-white bg-black/25'"><Check v-if="isPicked(g)" :size="16" :stroke-width="2.5" /></span>
        </component>
      </li>
    </ul>
    <!-- once this comes within 1200px, the next tiles are added (a new one after each batch) -->
    <div v-if="shown.length < sorted.length" :key="shown.length" ref="more" class="h-px" aria-hidden="true" />
  </div>
</template>
