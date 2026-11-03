<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { AArrowDown, AArrowUp } from '@lucide/vue'
import { coverWash } from '../coverColor'
import { useLyrics } from '../stores/lyrics'
import { usePlayer } from '../stores/player'
import { LYRICS_SIZES, useUi } from '../stores/ui'

// Synced (LRC) lyrics follow playback: the current line is highlighted and kept in the
// middle; tapping a line seeks there. Plain lyrics just scroll. `large`: the PC player; `bold`: the
// phone player (big bold lines on the cover's colours, which it paints itself).
// Behind it a light, see-through wash of the album art's colour; A-/A+ change the text size (kept).
const props = defineProps<{ large?: boolean; bold?: boolean }>()
const { t } = useI18n()
const player = usePlayer()
const lyrics = useLyrics()
const ui = useUi()
const box = ref<HTMLElement | null>(null)
const lines = ref<HTMLElement[]>([])

const wash = ref<string | null>(null)
watch(
  () => [player.current?.album_id, player.current?.cover_v, player.current?.has_cover] as const,
  async ([albumId, v, hasCover]) => {
    wash.value = albumId && hasCover && !props.bold ? await coverWash(albumId, v) : null
  },
  { immediate: true },
)
const scale = computed(() => LYRICS_SIZES[ui.playerPrefs.lyricsSize] ?? 1)
function resize(by: number) {
  ui.playerPrefs.lyricsSize = Math.min(LYRICS_SIZES.length - 1, Math.max(0, (ui.playerPrefs.lyricsSize ?? 2) + by))
  void nextTick(() => center(false))
}

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
  <div
    class="relative h-full overflow-hidden"
    :class="large ? 'rounded-3xl' : ''"
  >
    <div v-if="wash" class="pointer-events-none absolute inset-0 transition-[background] duration-500" :style="{ background: wash }" aria-hidden="true" />
    <!-- data-no-swipe: a swipe here scrolls the lyrics, it doesn't close the player (swipe.ts) -->
    <!-- lines fade out towards the top and bottom edges instead of running into what is around -->
    <div ref="box" data-no-swipe class="relative h-full overflow-y-auto overscroll-contain [mask-image:linear-gradient(to_bottom,transparent,black_14%,black_86%,transparent)] [scrollbar-width:none]" :class="[large ? 'px-8' : bold ? 'px-0' : 'px-6', lyrics.lyrics?.synced ? '' : 'py-10']">
      <p v-if="lyrics.loading" class="pt-10 text-center text-[15px] text-muted">{{ t('player.lyricsLoading') }}</p>
      <p v-else-if="!lyrics.lyrics?.synced && !lyrics.lyrics?.plain" class="pt-10 text-center text-[15px] text-muted">{{ t('player.noLyrics') }}</p>
      <!-- synced: room above and below (a share of the panel's height) so the first and last lines can sit in the middle -->
      <template v-else-if="lyrics.lyrics.synced">
        <div class="h-[40%]" aria-hidden="true" />
        <ol class="flex flex-col" :class="large || bold ? 'gap-5' : 'gap-3.5'">
          <li v-for="([time, line], i) in lyrics.lyrics.synced" :key="i" ref="lines">
            <button
              type="button"
              class="w-full origin-left text-left leading-snug transition-[color,transform] duration-300"
              :class="[
                large || bold ? 'font-bold' : '',
                i === lyrics.activeIndex ? (large || bold ? 'text-ink' : 'font-semibold text-ink') : bold ? 'text-ink/35' : 'text-ink/30 hover:text-ink/60',
                (large || bold) && i === lyrics.activeIndex ? 'scale-[1.02]' : '',
              ]"
              :style="{ fontSize: `${(large ? 28 : bold ? 27 : 19) * scale}px` }"
              @click="player.seek(time)"
            >
              <!-- the line, then (smaller) how it is read and its translation when the lyrics have them -->
              <template v-for="(part, k) in (line || '♪').split('\n')" :key="k">
                <span v-if="k === 0" class="block">{{ part }}</span>
                <span v-else class="mt-0.5 block text-[0.78em] font-normal">{{ part }}</span>
              </template>
            </button>
          </li>
        </ol>
        <div class="h-[40%]" aria-hidden="true" />
      </template>
      <p v-else class="whitespace-pre-line leading-relaxed text-ink/80" :style="{ fontSize: `${(large ? 20 : 17) * scale}px` }">{{ lyrics.lyrics.plain }}</p>
    </div>
    <!-- text size -->
    <!-- phone: top left (the close button is top right); PC: bottom right -->
    <div class="absolute flex gap-1" :class="large ? 'bottom-2.5 right-2.5' : bold ? 'bottom-2 right-0' : 'left-3 top-1'">
      <button
        v-for="by in [-1, 1]"
        :key="by"
        type="button"
        class="grid size-9 place-items-center rounded-full text-ink backdrop-blur-sm disabled:opacity-40"
        :class="bold ? 'bg-white/15' : 'bg-bg/60'"
        :aria-label="t(by < 0 ? 'player.lyricsSmaller' : 'player.lyricsLarger')"
        :disabled="by < 0 ? ui.playerPrefs.lyricsSize <= 0 : ui.playerPrefs.lyricsSize >= LYRICS_SIZES.length - 1"
        @click="resize(by)"
      >
        <component :is="by < 0 ? AArrowDown : AArrowUp" :size="18" :stroke-width="1.6" />
      </button>
    </div>
  </div>
</template>
