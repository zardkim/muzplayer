<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ArrowDown, ArrowUp, ChevronDown, ChevronUp, GripVertical, X } from '@lucide/vue'
import { duration } from '../format'
import { usePlayer } from '../stores/player'
import CoverArt from './CoverArt.vue'

// The play queue: what's playing, then what comes next. Songs already played fold away above.
// Reorder by dragging (mouse) or with the arrows (touch, keyboard); a click plays that song.
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
  box.value?.querySelector('[data-current]')?.scrollIntoView({ block: 'start' })
})

// drag and drop (pointer devices); the drop target is the row under the pointer
const dragFrom = ref<number | null>(null)
const dragOver = ref<number | null>(null)
function drop(to: number) {
  if (dragFrom.value !== null && dragFrom.value !== to) player.move(dragFrom.value, to)
  dragFrom.value = dragOver.value = null
}
</script>

<template>
  <div ref="box" class="flex flex-col">
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
          class="group flex items-center gap-2.5 rounded-xl px-2 transition-colors"
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
