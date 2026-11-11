<script setup lang="ts">
import SourceLogo from './SourceLogo.vue'
import { sourceLogo } from '../format'
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, coverUrl } from '../api'
import { coverColor } from '../coverColor'
import { usePlayer } from '../stores/player'
import type { Chart, ChartDetail } from '../types'
import PlayerIcons from './PlayerIcons.vue'

// A wide banner for a chart week or a theme: its banner image (AI-made or the folder's
// banner.jpg), or one drawn from the top covers. The text always sits on top as HTML.
const props = withDefaults(defineProps<{ chart: Chart; image?: string | null; link?: boolean; size?: 'hero' | 'compact' | 'header' | 'small' }>(), {
  image: undefined,
  link: true,
  size: 'hero',
})
const { t } = useI18n()
const player = usePlayer()

const src = computed(() => (props.image !== undefined ? props.image : props.chart.banner?.url ?? null))
const failed = ref(false)
watch(src, () => (failed.value = false))
const covers = computed(() => props.chart.cover_albums.slice(0, 4))

const tint = ref<string | null>(null)
watch(
  () => props.chart.cover_albums[0],
  async (c) => (tint.value = c ? await coverColor(c.id, c.v) : null),
  { immediate: true },
)

const label = computed(() =>
  props.chart.kind === 'chart'
    ? props.chart.source || t('charts.chart')
    : props.chart.source || t('charts.theme'),
)

async function play() {
  const detail = await api<ChartDetail>(`/charts/${props.chart.id}`)
  player.playTracks(detail.tracks, 0, { shuffle: false })
}
</script>

<template>
  <component
    :is="link ? 'RouterLink' : 'div'"
    :to="link ? { name: 'chart', params: { id: chart.id } } : undefined"
    class="relative block overflow-hidden rounded-2xl bg-[#111113] text-white"
    :class="{ small: 'aspect-[16/9]', compact: 'aspect-[2/1] md:aspect-[4/1]', header: 'aspect-[16/9] md:aspect-[5/2]', hero: 'aspect-[16/9] md:aspect-[3/1]' }[size]"
    :style="{ '--tint': tint ?? '38 38 44' }"
  >
    <img v-if="src && !failed" :src="src" alt="" class="absolute inset-0 h-full w-full object-cover" @error="failed = true" />
    <template v-else>
      <!-- drawn from the covers: tinted backdrop, a fanned stack on the right -->
      <div class="absolute inset-0 bg-[radial-gradient(120%_120%_at_85%_20%,rgb(var(--tint)/0.65),rgb(var(--tint))_55%,rgb(12_12_14))]" />
      <div class="pointer-events-none absolute inset-y-0 right-[4%] isolate w-[58%]" aria-hidden="true">
        <img
          v-for="(c, i) in covers"
          :key="c.id"
          :src="coverUrl(c.id, size === 'small' ? 'thumb' : 'large', c.v)"
          alt=""
          loading="lazy"
          class="absolute top-1/2 aspect-square h-[66%] rounded-lg object-cover shadow-[0_14px_36px_rgba(0,0,0,0.45)]"
          :style="{
            right: `${i * 17}%`,
            transform: `translateY(${-50 + (i % 2 ? 8 : -6)}%) rotate(${[4, -5, 6, -3][i]}deg)`,
            zIndex: 10 - i,
            opacity: 1 - i * 0.12,
          }"
        />
      </div>
    </template>

    <div class="absolute inset-0 bg-gradient-to-tr from-black/70 via-black/15 to-transparent" />
    <div class="absolute inset-x-0 bottom-0 flex items-end gap-3 p-4 md:p-6" :class="size === 'small' ? 'p-3' : ''">
      <div class="flex min-w-0 flex-1 flex-col gap-0.5">
        <span class="flex w-fit items-center gap-1 rounded-full bg-white/20 py-0.5 pr-2 text-[12px] font-medium backdrop-blur-sm" :class="sourceLogo(chart.source) ? 'pl-0.5' : 'pl-2'"><SourceLogo :source="chart.source" :size="18" class="rounded-full" />{{ label }}</span>
        <span
          class="line-clamp-2 font-bold leading-tight [text-shadow:0_1px_12px_rgba(0,0,0,0.35)]"
          :class="size === 'small' ? 'text-[17px]' : size === 'compact' ? 'text-[20px] md:text-[24px]' : 'text-[22px] md:text-[30px]'"
        >{{ chart.title }}</span>
        <span class="text-[13px] text-white/80">{{ t('common.tracks', chart.track_count) }}</span>
      </div>
      <button
        v-if="link"
        type="button"
        class="grid flex-none place-items-center rounded-full bg-bg text-ink shadow-lg transition-transform active:scale-90"
        :class="size === 'small' ? 'size-10' : 'size-12'"
        :aria-label="`${t('common.play')}: ${chart.title}`"
        @click.prevent.stop="play"
      >
        <PlayerIcons name="play" :size="size === 'small' ? 16 : 20" :stroke="2" />
      </button>
    </div>
    <slot />
  </component>
</template>
