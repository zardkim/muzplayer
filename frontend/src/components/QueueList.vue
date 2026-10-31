<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ArrowDown, ArrowUp, ChevronDown, ChevronUp, GripVertical, X } from '@lucide/vue'
import { duration } from '../format'
import { usePlayer } from '../stores/player'
import { useLongPress, useSwipe } from '../swipe'
import CoverArt from './CoverArt.vue'

// The play queue: what's playing, then what comes next. Songs already played fold away above.
// Reorder by dragging (mouse; on a phone hold a row, then drag) or with the arrows (keyboard);
// a click plays that song; on a phone a row swiped left leaves the queue.
const { t } = useI18n()
const player = usePlayer()
const showPlayed = ref(false)
const box = ref<HTMLElement | null>(null)

const playedCount = computed(() => Math.max(0, player.index))
const upcomingCount = computed(() => player.queue.length - player.index - 1)
// rows shown: played songs only when unfolded, then the current one and the rest
const rows = computed(() =>
  player.queue.map((track, i) => ({ track, i })).filter(({ i }) => showPlayed.value || i >= player.index),
)

onMounted(async () => {
  await nextTick()
  // scroll this list only (scrollIntoView would also move the page around it)
  const el = box.value?.querySelector('[data-current]')
  if (box.value && el) box.value.scrollTop += el.getBoundingClientRect().top - box.value.getBoundingClientRect().top
})

// drag and drop (pointer devices); the drop target is the row under the pointer
const dragFrom = ref<number | null>(null)
const dragOver = ref<number | null>(null)
function drop(to: number) {
  if (dragFrom.value !== null && dragFrom.value !== to) player.move(dragFrom.value, to)
  dragFrom.value = dragOver.value = null
}

// touch: one set of handlers for the list, the row found from the touch
let row: HTMLElement | null = null
const rowAt = (el: Element | null) => el?.closest<HTMLElement>('[data-row]') ?? null
const swipe = useSwipe({
  axes: ['x'],
  allow: (_, dx) => dx < 0 && !!row && Number(row.dataset.row) !== player.index && dragFrom.value === null,
  move: (_, dx) => row && (row.style.transform = `translateX(${Math.max(-140, dx)}px)`),
  end: ({ dx, fast }) => {
    const el = row
    if (!el) return
    el.style.transition = 'transform 0.18s ease-out'
    const gone = dx < -110 || (fast && dx < -40)
    el.style.transform = gone ? 'translateX(-110%)' : ''
    window.setTimeout(() => {
      el.style.transition = el.style.transform = ''
      if (gone) player.removeAt(Number(el.dataset.row))
    }, 180)
  },
})
const hold = useLongPress((target) => {
  const el = rowAt(target)
  if (el && Number(el.dataset.row) !== player.index) dragFrom.value = dragOver.value = Number(el.dataset.row)
})
function touchstart(e: TouchEvent) {
  row = rowAt(e.target as Element)
  if (!row) return
  swipe.onTouchstart(e)
  hold.onTouchstart(e)
}
function touchmove(e: TouchEvent) {
  if (dragFrom.value !== null) {
    // picked up: the row under the finger is where it goes (the list doesn't scroll meanwhile)
    if (e.cancelable) e.preventDefault()
    const t = e.touches[0]
    const over = rowAt(document.elementFromPoint(t.clientX, t.clientY))
    if (over) dragOver.value = Number(over.dataset.row)
    return
  }
  hold.onTouchmove(e)
  swipe.onTouchmove(e)
}
function touchend(e: TouchEvent) {
  hold.onTouchend()
  if (dragFrom.value !== null) {
    if (dragOver.value !== null && dragOver.value !== player.index) drop(dragOver.value)
    dragFrom.value = dragOver.value = null
    return
  }
  swipe.onTouchend(e)
}
</script>

<template>
  <div ref="box" class="flex flex-col" @touchstart="touchstart" @touchmove="touchmove" @touchend="touchend" @touchcancel="touchend" @click.capture="hold.onClickCapture">
    <p v-if="!player.queue.length" class="px-3 py-2 text-[15px] font-light text-muted">{{ t('player.queueEmpty') }}</p>

    <template v-else>
      <button
        v-if="playedCount"
        type="button"
        class="flex h-10 items-center gap-1.5 self-start rounded-full px-3 text-[13px] text-muted hover:bg-surface"
        :aria-expanded="showPlayed"
        @click="showPlayed = !showPlayed"
      >
        <ChevronUp v-if="showPlayed" :size="16" /><ChevronDown v-else :size="16" />
        {{ t('player.playedCount', { n: playedCount }) }}
      </button>

      <template v-for="{ track, i } in rows" :key="`${track.id}-${i}`">
        <h3 v-if="i === player.index + 1" class="px-3 pb-1 pt-4 text-[13px] font-medium text-muted">
          {{ t('player.upNextCount', { n: upcomingCount }) }}
        </h3>
        <div
          :data-current="i === player.index ? '' : undefined"
          :data-row="i"
          class="group flex items-center gap-2.5 rounded-xl px-2 transition-colors [-webkit-touch-callout:none]"
          :class="[
            i === player.index ? 'bg-accent-soft' : 'hover:bg-surface',
            dragOver === i && dragFrom !== i ? 'ring-2 ring-accent/40' : '',
            dragFrom === i ? 'opacity-40' : '',
          ]"
          :draggable="i !== player.index"
          @dragstart="(e) => { dragFrom = i; e.dataTransfer?.setData('text/plain', String(i)) }"
          @dragover.prevent="dragOver = i"
          @dragleave="dragOver === i && (dragOver = null)"
          @drop.prevent="drop(i)"
          @dragend="dragFrom = dragOver = null"
        >
          <GripVertical v-if="i !== player.index" :size="16" class="hidden flex-none cursor-grab text-subtle opacity-0 group-hover:opacity-100 md:block" aria-hidden="true" />
          <span v-else class="hidden w-4 flex-none md:block" />
          <button type="button" class="flex min-w-0 flex-1 items-center gap-3 py-2 text-left" @click="player.jump(i)">
            <CoverArt :album-id="track.album_id" :has-cover="track.has_cover" :version="track.cover_v" rounded="rounded-md" class="size-10 flex-none" />
            <span class="flex min-w-0 flex-col">
              <span class="truncate text-[15px]" :class="i === player.index ? 'font-medium text-accent' : i < player.index ? 'text-muted' : ''">{{ track.title }}</span>
              <span class="truncate text-[13px] font-light text-muted">{{ track.artist || t('common.unknownArtist') }} · {{ duration(track.duration) }}</span>
            </span>
          </button>
          <span v-if="i === player.index" class="flex-none pr-2 text-[12px] font-medium text-accent">{{ t('player.nowPlayingShort') }}</span>
          <span v-else class="flex flex-none items-center md:opacity-0 md:group-hover:opacity-100 md:group-focus-within:opacity-100">
            <button type="button" class="grid size-9 place-items-center rounded-full text-muted hover:bg-bg hover:text-ink disabled:opacity-30" :disabled="i === 0" :aria-label="t('common.moveUp')" @click="player.move(i, i - 1)"><ArrowUp :size="16" /></button>
            <button type="button" class="grid size-9 place-items-center rounded-full text-muted hover:bg-bg hover:text-ink disabled:opacity-30" :disabled="i === player.queue.length - 1" :aria-label="t('common.moveDown')" @click="player.move(i, i + 1)"><ArrowDown :size="16" /></button>
            <button type="button" class="grid size-9 place-items-center rounded-full text-muted hover:bg-bg hover:text-danger" :aria-label="t('common.remove')" @click="player.removeAt(i)"><X :size="16" /></button>
          </span>
        </div>
      </template>
      <p v-if="player.index >= 0 && !upcomingCount" class="px-3 pt-4 text-[13px] font-light text-muted">{{ t('player.queueEnd') }}</p>
    </template>
  </div>
</template>
