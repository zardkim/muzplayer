<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { usePlayer } from '../stores/player'
import type { Lyrics } from '../types'

// Synced (LRC) lyrics follow playback: the current line is highlighted and kept in the
// middle; tapping a line seeks there. Plain lyrics just scroll.
const props = defineProps<{ lyrics: Lyrics | null; loading: boolean }>()
const { t } = useI18n()
const player = usePlayer()
const box = ref<HTMLElement | null>(null)
const lines = ref<HTMLElement[]>([])

const active = computed(() => {
  const synced = props.lyrics?.synced
  if (!synced) return -1
  const now = player.currentTime + 0.2
  let i = -1
  while (i + 1 < synced.length && synced[i + 1][0] <= now) i++
  return i
})

watch(active, async (i) => {
  await nextTick()
  const el = lines.value[i]
  if (!box.value || !el) return
  box.value.scrollTo({ top: el.offsetTop - box.value.clientHeight / 2 + el.clientHeight / 2, behavior: 'smooth' })
})
watch(() => props.lyrics, () => box.value?.scrollTo({ top: 0 }))
</script>

<template>
  <div ref="box" class="relative h-full overflow-y-auto overscroll-contain px-6 [scrollbar-width:none]" :class="lyrics?.synced ? 'py-[40%]' : 'py-10'">
    <p v-if="loading" class="text-center text-[15px] text-muted">{{ t('common.loading') }}</p>
    <p v-else-if="!lyrics?.synced && !lyrics?.plain" class="text-center text-[15px] text-muted">{{ t('player.noLyrics') }}</p>
    <ol v-else-if="lyrics.synced" class="flex flex-col gap-3.5">
      <li v-for="([time, line], i) in lyrics.synced" :key="i" ref="lines">
        <button
          type="button"
          class="w-full text-left text-[19px] leading-snug transition-colors"
          :class="i === active ? 'font-semibold text-ink' : 'text-ink/35 hover:text-ink/60'"
          @click="player.seek(time)"
        >
          {{ line || '♪' }}
        </button>
      </li>
    </ol>
    <p v-else class="whitespace-pre-line text-[17px] leading-relaxed text-ink/80">{{ lyrics.plain }}</p>
  </div>
</template>
