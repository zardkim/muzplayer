<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { Clapperboard, Disc3, Layers, Scissors } from '@lucide/vue'
import { useUi } from '../stores/ui'
import QualityBadge from './QualityBadge.vue'

// An album's kind (compilation, soundtrack, unofficial, extracted) and sound (Hi-Res, Lossless, or its
// lossy format: MP3, AAC...), each in its own colour and icon, so they read at a glance in a grid.
// Filled with fixed colours and white text: the same in every theme. The sound ones follow Settings
// → album quality badge.
const props = defineProps<{ kind?: string | null; quality?: 'hires' | 'lossless' | null; format?: string | null; large?: boolean; extracted?: boolean }>()
const { t } = useI18n()
const ui = useUi()

const KINDS: Record<string, { icon: unknown; color: string }> = {
  compilation: { icon: Layers, color: 'bg-[#2f6bd1]' },
  soundtrack: { icon: Clapperboard, color: 'bg-[#8247d1]' },
  unofficial: { icon: Disc3, color: 'bg-[#b8641a]' },
  extracted: { icon: Scissors, color: 'bg-[#5b6472]' },
}
const LOSSY: Record<string, string> = { mp3: 'MP3', m4a: 'AAC', mp4: 'AAC', aac: 'AAC', ogg: 'OGG', oga: 'OGG', opus: 'OPUS', wma: 'WMA' }
const kindBadge = computed(() => (props.kind && (props.kind !== 'extracted' || props.extracted) ? KINDS[props.kind] : undefined))
const lossy = computed(() => (!props.quality && props.format ? LOSSY[props.format.toLowerCase()] : undefined))
const size = computed(() => (props.large ? 'h-6 px-2 text-[12px]' : 'h-[18px] px-1 text-[11px]'))
</script>

<template>
  <span v-if="kindBadge" class="flex flex-none items-center gap-0.5 rounded font-medium text-white" :class="[kindBadge.color, size]">
    <component :is="kindBadge.icon" :size="large ? 13 : 11" :stroke-width="2" aria-hidden="true" />{{ t(`albums.kind_${kind}`) }}
  </span>
  <span v-if="quality === 'lossless' && ui.playerPrefs.showQuality" class="flex flex-none items-center rounded bg-[#0f8a6c] font-semibold text-white" :class="size">{{ t('albums.quality_lossless') }}</span>
  <QualityBadge v-else-if="quality === 'hires'" :quality="quality" :large="large" />
  <span v-else-if="lossy && ui.playerPrefs.showQuality" class="flex flex-none items-center rounded border border-line-strong font-medium text-muted" :class="size">{{ lossy }}</span>
</template>
