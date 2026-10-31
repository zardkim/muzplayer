<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useUi } from '../stores/ui'

// Hi-Res / Lossless on an album (Settings → album quality badge)
defineProps<{ quality?: 'hires' | 'lossless' | null }>()
const { t } = useI18n()
const ui = useUi()
</script>

<template>
  <span
    v-if="quality && ui.playerPrefs.showQuality"
    class="flex-none rounded px-1 text-[11px] font-medium leading-[18px]"
    :class="quality === 'hires' ? 'bg-accent text-white' : 'border border-line-strong'"
  >{{ t(`albums.quality_${quality}`) }}</span>
</template>
