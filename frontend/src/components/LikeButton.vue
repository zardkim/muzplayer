<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { Heart } from '@lucide/vue'
import { errorMessage } from '../i18n'
import { useLibrary } from '../stores/library'
import { useUi } from '../stores/ui'
import type { Track } from '../types'

// The like (heart) button of the players: a liked song's heart is filled red (--color-like). With a
// mouse it turns red and grows a little on hover, so it is clear what a click will do.
const props = withDefaults(defineProps<{ track: Track; size?: number; box?: string }>(), { size: 22, box: 'size-11' })
const { t } = useI18n()
const library = useLibrary()
const ui = useUi()

async function toggle() {
  try {
    await library.toggleFavorite(props.track)
  } catch (e) {
    ui.notify(errorMessage(e), true)
  }
}
</script>

<template>
  <button
    type="button"
    class="group grid flex-none place-items-center rounded-full transition-colors hover:bg-like/10 hover:text-like"
    :class="[box, library.isFavorite(track) ? 'text-like' : 'text-ink']"
    :aria-label="library.isFavorite(track) ? t('common.favoriteRemove') : t('common.favoriteAdd')"
    :aria-pressed="library.isFavorite(track)"
    @click="toggle"
  >
    <Heart
      :size="size"
      :stroke-width="1.3"
      :fill="library.isFavorite(track) ? 'currentColor' : 'none'"
      class="transition-transform duration-150 group-hover:scale-110 group-active:scale-90"
    />
  </button>
</template>
