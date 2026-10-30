<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useLyrics } from '../stores/lyrics'
import { usePlayer } from '../stores/player'

// Synced (LRC) lyrics follow playback: the current line is highlighted and kept in the
// middle; tapping a line seeks there. Plain lyrics just scroll. `large`: the PC player.
defineProps<{ large?: boolean }>()
const { t } = useI18n()
const player = usePlayer()
const lyrics = useLyrics()
const box = ref<HTMLElement | null>(null)
const lines = ref<HTMLElement[]>([])

function center(smooth: boolean) {
  const el = lines.value[lyrics.activeIndex]
  if (!box.value || !el) return
  box.value.scrollTo({ top: el.offsetTop - box.value.clientHeight / 2 + el.clientHeight / 2, behavior: smooth ? 'smooth' : 'auto' })
}
watch(() => lyrics.activeIndex, async () => {
  await nextTick()
  center(true)
})
watch(() => lyrics.lyrics, async () => {
  box.value?.scrollTo({ top: 0 })
  await nextTick()
  center(false) // opened mid-song: jump straight to the line being sung
}, { immediate: true })
</script>

<template>
  <div ref="box" class="relative h-full overflow-y-auto overscroll-contain [scrollbar-width:none]" :class="[large ? 'px-2' : 'px-6', lyrics.lyrics?.synced ? '' : 'py-10']">
    <p v-if="lyrics.loading" class="text-center text-[15px] text-muted">{{ t('common.loading') }}</p>
    <p v-else-if="!lyrics.lyrics?.synced && !lyrics.lyrics?.plain" class="text-center text-[15px] text-muted">{{ t('player.noLyrics') }}</p>
    <!-- synced: room above and below (a share of the panel's height) so the first and last lines can sit in the middle -->
    <template v-else-if="lyrics.lyrics.synced">
      <div class="h-[40%]" aria-hidden="true" />
      <ol class="flex flex-col" :class="large ? 'gap-5' : 'gap-3.5'">
        <li v-for="([time, line], i) in lyrics.lyrics.synced" :key="i" ref="lines">
          <button
            type="button"
            class="w-full origin-left text-left leading-snug transition-[color,transform] duration-300"
            :class="[
              large ? 'text-[28px] font-bold' : 'text-[19px]',
              i === lyrics.activeIndex ? (large ? 'text-ink' : 'font-semibold text-ink') : 'text-ink/30 hover:text-ink/60',
              large && i === lyrics.activeIndex ? 'scale-[1.02]' : '',
            ]"
            @click="player.seek(time)"
          >
            {{ line || '♪' }}
          </button>
        </li>
      </ol>
      <div class="h-[40%]" aria-hidden="true" />
    </template>
    <p v-else class="whitespace-pre-line leading-relaxed text-ink/80" :class="large ? 'text-[20px]' : 'text-[17px]'">{{ lyrics.lyrics.plain }}</p>
  </div>
</template>
