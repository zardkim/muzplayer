<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { ChevronDown, ListOrdered, Moon } from '@lucide/vue'
import { duration, longDuration } from '../format'
import { SPEEDS, usePlayer } from '../stores/player'
import { useUi } from '../stores/ui'
import { SETTLE, usePullToClose, useSwipe } from '../swipe'
import BookCover from './BookCover.vue'
import PlayerIcons from './PlayerIcons.vue'
import SeekBar from './SeekBar.vue'
import SkipIcon from './SkipIcon.vue'
import Marquee from './Marquee.vue'

// Full-screen player while an audiobook plays (NowPlaying is the music one).
const { t } = useI18n()
const player = usePlayer()
const ui = useUi()
const preview = ref<number | null>(null)
const sheet = ref<'speed' | 'sleep' | 'chapters' | null>(null)

// seek bar covers the current chapter (or the whole book without chapters)
const segLength = computed(() => Math.max(0, player.segment.end - player.segment.start))
const segPos = computed(() => Math.min(segLength.value, Math.max(0, player.bookPos - player.segment.start)))
const bookLeft = computed(() => Math.max(0, (player.book?.duration ?? 0) - player.bookPos) / player.rate)

// ticks once a second for the sleep timer countdown
const now = ref(Date.now())
let tick: number | undefined
onMounted(() => (tick = window.setInterval(() => (now.value = Date.now()), 1000)))
onUnmounted(() => clearInterval(tick))
const sleepLabel = computed(() => {
  if (player.sleepChapter !== null) return t('player.sleepAtChapterEnd')
  if (player.sleepUntil !== null) return duration(Math.max(0, (player.sleepUntil - now.value) / 1000))
  return t('player.sleep')
})

const chapterList = ref<HTMLElement | null>(null)
watch(sheet, async (s) => {
  if (s !== 'chapters') return
  await nextTick()
  chapterList.value?.querySelector('[aria-current="true"]')?.scrollIntoView({ block: 'center' })
})

function pickSleep(value: number | 'chapter' | null) {
  player.setSleep(value)
  sheet.value = null
}

// gestures (phones): pull the player down to tuck it away; swipe the cover left to skip ahead,
// right to go back (Settings → audiobooks sets by how much)
const scroller = ref<HTMLElement | null>(null)
const coverX = ref(0)
const { dragY, settling, settle, pull } = usePullToClose(() => (ui.playerOpen = false), () => (scroller.value?.scrollTop ?? 0) <= 0)
const flick = useSwipe({
  axes: ['x'],
  move: (_, dx) => (coverX.value = Math.max(-80, Math.min(80, dx * 0.5))),
  end: ({ dx, fast }) => {
    settle(() => (coverX.value = 0))
    if (Math.abs(dx) < 70 && !(fast && Math.abs(dx) > 30)) return
    const secs = dx < 0 ? player.skipForward : -player.skipBack
    player.skip(secs)
    ui.notify(t(dx < 0 ? 'player.skippedForward' : 'player.skippedBack', { n: Math.abs(secs) }))
  },
})
</script>

<template>
  <div
    v-if="player.book"
    role="dialog"
    aria-modal="true"
    :aria-label="t('player.nowPlaying')"
    ref="scroller"
    class="fixed inset-0 z-50 overflow-y-auto bg-sheet text-ink"
    :class="[dragY ? 'overflow-hidden' : '', settling ? SETTLE : '']"
    :style="dragY ? { transform: `translate3d(0,${dragY}px,0)` } : undefined"
    @touchstart="pull.onTouchstart"
    @touchmove="pull.onTouchmove"
    @touchend="pull.onTouchend"
    @touchcancel="pull.onTouchcancel"
  >
    <div
      class="relative mx-auto flex min-h-full max-w-md flex-col px-5 pt-[calc(env(safe-area-inset-top)+8px)] md:my-6 md:min-h-0 md:rounded-3xl md:shadow-2xl"
    >
      <div class="relative z-10 flex justify-end">
        <button type="button" class="-mb-6 grid size-11 place-items-center rounded-full bg-bg/70" :aria-label="t('player.close')" @click="ui.playerOpen = false">
          <ChevronDown :size="24" :stroke-width="1.4" />
        </button>
      </div>

      <!-- 2:3 cover: capped by height so the controls below stay on screen -->
      <div
        class="flex justify-center"
        :class="settling ? SETTLE : ''"
        :style="coverX ? { transform: `translateX(${coverX}px)` } : undefined"
        @touchstart="flick.onTouchstart"
        @touchmove="flick.onTouchmove"
        @touchend="flick.onTouchend"
        @touchcancel="flick.onTouchcancel"
      >
        <BookCover :book-id="player.book.id" :has-cover="player.book.has_cover" :version="player.book.cover_v" size="large" rounded="rounded-xl" class="w-[min(62%,27dvh)] shadow-[0_12px_40px_rgba(17,17,19,0.18)]" />
      </div>

      <div class="mt-4 flex flex-col items-center gap-1 text-center">
        <Marquee :text="player.chapter?.title || player.book.title" class="text-[22px] font-medium leading-snug" />
        <RouterLink :to="{ name: 'book', params: { id: player.book.id } }" class="line-clamp-1 text-[15px] font-light text-soft">
          {{ player.chapter ? player.book.title : player.book.authors || t('books.unknownAuthor') }}
        </RouterLink>
      </div>

      <div class="mt-3">
        <SeekBar
          :value="segPos"
          :max="segLength"
          :label="t('player.seek')"
          track="color-mix(in srgb, var(--color-ink) 12%, transparent)"
          @change="(v) => player.seekBook(player.segment.start + v)"
          @preview="(v) => (preview = v)"
        />
        <div class="mt-1 flex items-center justify-between font-display text-sm text-soft">
          <span>{{ duration(preview ?? segPos) }}</span>
          <span v-if="player.chapters.length" class="text-[12px]">{{ t('books.chapterOf', { n: player.chapterIndex + 1, total: player.chapters.length }) }}</span>
          <span>-{{ duration(segLength - (preview ?? segPos)) }}</span>
        </div>
      </div>

      <div class="mt-2 flex items-center justify-between">
        <button type="button" class="grid size-12 place-items-center" :aria-label="t('player.prevChapter')" @click="player.prevChapter()">
          <PlayerIcons name="prev" :size="26" :stroke="1.2" />
        </button>
        <button type="button" class="grid size-14 place-items-center" :aria-label="t('player.skipBack', { n: player.skipBack })" @click="player.skip(-player.skipBack)">
          <SkipIcon :seconds="player.skipBack" :size="38" />
        </button>
        <button
          type="button"
          class="grid size-[76px] place-items-center rounded-full bg-ink text-on-ink transition-transform active:scale-90"
          :aria-label="player.playing ? t('player.pause') : t('player.play')"
          @click="player.toggle()"
        >
          <PlayerIcons :name="player.playing ? 'pause' : 'play'" :size="34" :stroke="1.6" />
        </button>
        <button type="button" class="grid size-14 place-items-center" :aria-label="t('player.skipForward', { n: player.skipForward })" @click="player.skip(player.skipForward)">
          <SkipIcon :seconds="player.skipForward" forward :size="38" />
        </button>
        <button type="button" class="grid size-12 place-items-center" :aria-label="t('player.nextChapter')" @click="player.nextChapter()">
          <PlayerIcons name="next" :size="26" :stroke="1.2" />
        </button>
      </div>

      <p class="mt-2 text-center text-[13px] text-muted">{{ t('player.bookLeft', { time: longDuration(bookLeft) }) }}</p>

      <div class="mt-auto grid grid-cols-3 gap-2 pb-[calc(1.25rem+env(safe-area-inset-bottom))] pt-4">
        <button type="button" class="flex h-11 items-center justify-center gap-1.5 rounded-full border border-line-strong text-[14px]" :aria-label="t('player.speed')" @click="sheet = 'speed'">
          <span class="font-display font-semibold">{{ player.rate }}×</span>
        </button>
        <button
          type="button"
          class="flex h-11 items-center justify-center gap-1.5 rounded-full border text-[14px]"
          :class="player.sleepUntil !== null || player.sleepChapter !== null ? 'border-ink bg-ink text-on-ink' : 'border-line-strong'"
          @click="sheet = 'sleep'"
        >
          <Moon :size="16" :stroke-width="1.6" /><span class="truncate">{{ sleepLabel }}</span>
        </button>
        <button type="button" class="flex h-11 items-center justify-center gap-1.5 rounded-full border border-line-strong text-[14px] disabled:opacity-40" :disabled="!player.chapters.length" @click="sheet = 'chapters'">
          <ListOrdered :size="16" :stroke-width="1.6" />{{ t('books.chapters') }}
        </button>
      </div>
    </div>

    <!-- bottom sheets -->
    <div v-if="sheet" data-no-swipe class="fixed inset-0 z-[60] flex items-end justify-center bg-black/30" @click.self="sheet = null">
      <div class="pb-safe flex max-h-[75dvh] w-full max-w-md flex-col rounded-t-3xl bg-bg pt-2 shadow-2xl" role="dialog" aria-modal="true">
        <div class="mx-auto mb-2 h-1 w-10 rounded-full bg-line-strong" />
        <template v-if="sheet === 'speed'">
          <h2 class="px-5 pb-3 text-lg font-bold">{{ t('player.speed') }}</h2>
          <div class="grid grid-cols-4 gap-2 px-5 pb-6">
            <button
              v-for="s in SPEEDS"
              :key="s"
              type="button"
              class="h-11 rounded-full border font-display text-[15px]"
              :class="player.rate === s ? 'border-ink bg-ink text-on-ink' : 'border-line-strong'"
              :aria-pressed="player.rate === s"
              @click="(player.rate = s), (sheet = null)"
            >{{ s }}×</button>
          </div>
        </template>
        <template v-else-if="sheet === 'sleep'">
          <h2 class="px-5 pb-2 text-lg font-bold">{{ t('player.sleep') }}</h2>
          <div class="flex flex-col pb-4">
            <button v-for="m in [15, 30, 45, 60]" :key="m" type="button" class="px-5 py-3.5 text-left text-[16px] hover:bg-surface" @click="pickSleep(m)">{{ t('player.sleepMinutes', { n: m }) }}</button>
            <button type="button" class="px-5 py-3.5 text-left text-[16px] hover:bg-surface disabled:opacity-40" :disabled="!player.chapters.length" @click="pickSleep('chapter')">{{ t('player.sleepChapter') }}</button>
            <button v-if="player.sleepUntil !== null || player.sleepChapter !== null" type="button" class="px-5 py-3.5 text-left text-[16px] text-accent hover:bg-surface" @click="pickSleep(null)">{{ t('player.sleepOff') }}</button>
          </div>
        </template>
        <template v-else>
          <h2 class="px-5 pb-2 text-lg font-bold">{{ t('books.chapters') }}</h2>
          <ol ref="chapterList" class="overflow-y-auto pb-4">
            <li v-for="(c, i) in player.chapters" :key="i">
              <button
                type="button"
                class="flex w-full items-center gap-3 px-5 py-3 text-left hover:bg-surface"
                :class="i === player.chapterIndex ? 'text-accent' : ''"
                :aria-current="i === player.chapterIndex"
                @click="player.jumpChapter(i), (sheet = null)"
              >
                <span class="w-7 flex-none font-display text-[13px] text-muted">{{ i + 1 }}</span>
                <span class="min-w-0 flex-1 truncate text-[15px]">{{ c.title }}</span>
                <span class="font-display text-[13px] text-muted">{{ duration(c.end - c.start) }}</span>
              </button>
            </li>
          </ol>
        </template>
      </div>
    </div>
  </div>
</template>
