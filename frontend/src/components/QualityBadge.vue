<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useUi } from '../stores/ui'

// Hi-Res / Lossless on an album (Settings → album quality badge); Hi-Res wears the Hi-Res Audio logo
defineProps<{ quality?: 'hires' | 'lossless' | null; large?: boolean }>()
const { t } = useI18n()
const ui = useUi()
</script>

<template>
  <img
    v-if="quality === 'hires' && ui.playerPrefs.showQuality"
    src="/hires.png"
    :alt="t('albums.quality_hires')"
    :title="t('albums.quality_hires')"
    class="flex-none rounded-[3px]"
    :class="large ? 'size-7' : 'size-[18px]'"
  />
  <span
    v-else-if="quality && ui.playerPrefs.showQuality"
    class="flex-none rounded border border-line-strong px-1 text-[11px] font-medium leading-[18px]"
  >{{ t(`albums.quality_${quality}`) }}</span>
</template>
