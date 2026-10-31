<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, coverUrl } from '../api'
import type { Genre } from '../types'
import { useAuth } from '../stores/auth'
import LibraryHeader from '../components/LibraryHeader.vue'
import MergeSheet from '../components/MergeSheet.vue'

// Genres as colour tiles: each genre keeps its own colour (from its name), with the covers of
// its biggest albums fanned out in the corner. The largest genres get wide tiles up top.
const { t } = useI18n()
const auth = useAuth()
const merging = ref(false) // admin: the duplicates sheet
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
function colour(name: string) {
  let h = 0
  for (const ch of name) h = (h * 31 + ch.charCodeAt(0)) >>> 0
  return PALETTE[h % PALETTE.length]
}

const sorted = computed(() =>
  sort.value === 'size'
    ? [...items.value].sort((a, b) => b.track_count - a.track_count || a.name.localeCompare(b.name))
    : items.value,
)
// wide tiles for the four biggest genres (only when sorted by size and there are enough)
const wide = computed(() => (sort.value === 'size' && items.value.length >= 8 ? 4 : 0))
// fanned covers: back to front
const FAN = ['rotate-[-14deg] translate-x-[-58%]', 'rotate-[-2deg] translate-x-[-28%]', 'rotate-[16deg]']
const FAN_HOVER = ['group-hover:rotate-[-20deg] group-hover:translate-x-[-72%]', 'group-hover:rotate-[-4deg] group-hover:translate-x-[-34%]', 'group-hover:rotate-[22deg] group-hover:translate-x-[6%]']
</script>

<template>
  <div class="flex flex-col gap-6">
    <LibraryHeader :sub="loaded && items.length ? t('genres.count', items.length) : undefined">
      <div class="flex items-center gap-1 text-[14px]">
        <button v-if="auth.user?.is_admin" type="button" class="h-8 flex-none rounded-full border border-line-strong px-3 text-[13px] hover:border-ink" @click="merging = true">{{ t('merge.open') }}</button>
        <button
          v-for="s in (['size', 'name'] as const)"
          :key="s"
          type="button"
          class="h-8 rounded-full px-3"
          :class="sort === s ? 'bg-surface-2 font-medium' : 'font-light text-muted hover:text-ink'"
          @click="sort = s"
        >
          {{ t(`genres.sort_${s}`) }}
        </button>
      </div>
    </LibraryHeader>
    <p v-if="loaded && !items.length" class="font-light text-muted">{{ t('genres.empty') }}</p>
    <MergeSheet v-if="merging" kind="genre" @close="merging = false" @changed="load" />

    <ul class="grid grid-flow-dense grid-cols-2 gap-3 sm:grid-cols-[repeat(auto-fill,minmax(200px,1fr))] sm:gap-4">
      <li v-for="(g, i) in sorted" :key="g.id" :class="i < wide ? 'col-span-2' : ''">
        <RouterLink
          :to="{ name: 'tracks', query: { genre: g.id } }"
          class="group relative block overflow-hidden rounded-2xl text-white shadow-sm transition-transform duration-200 hover:-translate-y-0.5 hover:shadow-lg focus-visible:ring-2 focus-visible:ring-ink focus-visible:ring-offset-2"
          :class="i < wide ? 'aspect-[2.1/1]' : 'aspect-[1.35/1]'"
          :style="{ background: `linear-gradient(135deg, ${colour(g.name)} 0%, color-mix(in srgb, ${colour(g.name)} 72%, black) 100%)` }"
        >
          <span class="relative z-10 flex flex-col p-4" :class="i < wide ? 'md:p-5' : ''">
            <span class="font-bold leading-tight [text-wrap:balance]" :class="i < wide ? 'text-[26px] md:text-[30px]' : 'text-[20px]'">{{ g.name }}</span>
            <span class="mt-1 text-[13px] font-medium text-white/80">{{ t('common.tracks', g.track_count) }}</span>
          </span>
          <!-- the genre's biggest albums, fanned out in the corner -->
          <span v-if="g.covers?.length" class="absolute bottom-[-12%] right-[-6%] h-[62%] w-[42%]" aria-hidden="true">
            <img
              v-for="(c, k) in g.covers.slice(0, 3)"
              :key="c.id"
              :src="coverUrl(c.id, 'thumb', c.v)"
              alt=""
              loading="lazy"
              class="absolute bottom-0 right-0 aspect-square h-full rounded-lg object-cover shadow-[0_8px_20px_rgba(0,0,0,0.35)] transition-transform duration-300 ease-out"
              :class="[FAN[k + 3 - Math.min(3, g.covers.length)], FAN_HOVER[k + 3 - Math.min(3, g.covers.length)]]"
            />
          </span>
          <span v-else class="absolute bottom-3 right-4 text-[64px] font-black leading-none text-white/15" aria-hidden="true">#</span>
        </RouterLink>
      </li>
    </ul>
  </div>
</template>
