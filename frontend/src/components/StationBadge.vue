<script setup lang="ts">
import { computed } from 'vue'

// A radio station's mark: its logo (public/radio-logos, from Wikipedia/Commons; see docs/radio_logos.md)
// or, for the stations without one, its broadcaster's short name on a colour of its own.
// sized by its height (class), or by its width with `fill` (a card: as wide as its column)
const props = defineProps<{ stn: string; logo?: string | null; fill?: boolean }>()
const MARKS: Record<string, [string, string]> = {
  kbs: ['KBS', '#1f4e9c'], mbc: ['MBC', '#2b2b2b'], sbs: ['SBS', '#0b6bb5'], ebs: ['EBS', '#6aa52b'],
  cbs: ['CBS', '#d1342d'], tbn: ['TBN', '#0f8a7a'], febc: ['극동', '#5a3d8a'], bbs: ['BBS', '#c27a12'],
  wbs: ['원음', '#3d7a3a'], cpbc: ['평화', '#245a8f'], kugak: ['국악', '#8a3b2e'], afn: ['AFN', '#3b4a5a'],
  tbs: ['TBS', '#e2483d'], obs: ['OBS', '#2a5db0'], ifm: ['iFM', '#e07a1f'], ytn: ['YTN', '#174ea6'],
  befm: ['BeFM', '#1d8fbf'], ggn: ['경기', '#2f8f5b'], arirang: ['ARR', '#b3253a'], kookbang: ['국방', '#4b5d2e'],
  community: ['FM', '#6b6b6b'],
}
const mark = computed(() => MARKS[props.stn] ?? [props.stn.slice(0, 3).toUpperCase(), '#555'])
const shape = computed(() => (props.fill ? { width: '100%', height: 'auto', aspectRatio: '3 / 2' } : { width: 'auto', aspectRatio: '3 / 2' }))
</script>

<template>
  <img v-if="logo" :src="`/radio-logos/${logo}.png`" alt="" class="flex-none bg-white object-cover shadow-[0_0_0_1px_rgb(0_0_0/0.08)]" :class="fill ? 'rounded-2xl' : 'rounded-[18%]'" :style="shape" aria-hidden="true" />
  <span v-else class="grid flex-none place-items-center font-display font-bold text-white" :class="fill ? 'rounded-2xl' : 'rounded-[18%]'" :style="{ background: mark[1], ...shape }" aria-hidden="true">
    <span class="text-[0.8em] leading-none">{{ mark[0] }}</span>
  </span>
</template>
