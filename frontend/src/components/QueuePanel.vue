<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { X } from '@lucide/vue'
import { usePlayer } from '../stores/player'
import { useUi } from '../stores/ui'
import { useSwipe } from '../swipe'
import QueueList from './QueueList.vue'

// Side sheet with the queue (phone player, PC bottom bar). The PC player shows the same list in its tab.
const { t } = useI18n()
const player = usePlayer()
const ui = useUi()

// phones: swipe the panel right (the way it came in) to close it
const offset = ref(0)
const settling = ref(false)
const swipe = useSwipe({
  axes: ['x'],
  allow: (_, dx) => dx > 0,
  move: (_, dx) => (offset.value = Math.max(0, dx)),
  end: ({ dx, fast }) => {
    settling.value = true
    const close = dx > 110 || (fast && dx > 40)
    offset.value = close ? window.innerWidth : 0
    window.setTimeout(() => {
      settling.value = false
      if (close) ui.queueOpen = false
      offset.value = 0
    }, 200)
  },
})
</script>

<template>
  <div class="fixed inset-0 z-[60] flex justify-end bg-black/20" @click.self="ui.queueOpen = false" @keydown.esc="ui.queueOpen = false">
    <aside
      :aria-label="t('player.queue')"
      class="pt-safe pb-safe flex h-full w-full max-w-sm flex-col bg-bg shadow-2xl"
      :class="settling ? 'transition-transform duration-200 ease-out' : ''"
      :style="offset ? { transform: `translateX(${offset}px)` } : undefined"
      @touchstart="swipe.onTouchstart"
      @touchmove="swipe.onTouchmove"
      @touchend="swipe.onTouchend"
      @touchcancel="swipe.onTouchcancel"
    >
      <div class="flex items-center justify-between px-5 py-3">
        <h2 class="text-2xl font-bold">{{ t('player.queue') }}</h2>
        <div class="flex items-center gap-1">
          <button
            v-if="player.queue.length > player.index + 1"
            type="button"
            class="h-9 rounded-full border border-line-strong px-3 text-[13px] hover:bg-surface"
            @click="player.clearUpcoming()"
          >
            {{ t('player.clearQueue') }}
          </button>
          <button type="button" class="grid size-11 place-items-center rounded-full hover:bg-surface" :aria-label="t('common.close')" @click="ui.queueOpen = false">
            <X :size="22" :stroke-width="1.4" />
          </button>
        </div>
      </div>
      <QueueList class="flex-1 overflow-y-auto px-2 pb-4" />
    </aside>
  </div>
</template>
