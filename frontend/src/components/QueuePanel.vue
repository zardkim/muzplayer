<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { ArrowDown, ArrowUp, X } from '@lucide/vue'
import { duration } from '../format'
import { usePlayer } from '../stores/player'
import { useUi } from '../stores/ui'

const { t } = useI18n()
const player = usePlayer()
const ui = useUi()
</script>

<template>
  <aside
    :aria-label="t('player.queue')"
    class="pb-safe fixed inset-y-0 right-0 z-50 flex w-full max-w-sm flex-col border-l border-line bg-surface shadow-2xl shadow-black/50"
  >
    <div class="flex items-center justify-between border-b border-line px-5 py-3">
      <h2 class="text-lg font-bold">{{ t('player.queue') }}</h2>
      <div class="flex items-center gap-1">
        <button
          v-if="player.queue.length > player.index + 1"
          type="button"
          class="h-9 rounded-full px-3 text-[13px] text-muted hover:text-ink"
          @click="player.clearUpcoming()"
        >
          {{ t('player.clearQueue') }}
        </button>
        <button type="button" class="grid size-11 place-items-center text-muted hover:text-ink" :aria-label="t('common.close')" @click="ui.queueOpen = false">
          <X :size="20" />
        </button>
      </div>
    </div>
    <p v-if="!player.queue.length" class="p-5 text-sm text-muted">{{ t('player.queueEmpty') }}</p>
    <ol class="flex-1 overflow-y-auto p-2">
      <li
        v-for="(track, i) in player.queue"
        :key="`${track.id}-${i}`"
        class="group flex items-center gap-2 rounded-xl px-2"
        :class="i === player.index ? 'bg-surface-2' : 'hover:bg-surface-2/60'"
      >
        <button type="button" class="flex min-w-0 flex-1 flex-col py-2 text-left" @click="player.jump(i)">
          <span class="truncate text-sm font-semibold" :class="i === player.index ? 'text-accent' : i < player.index ? 'text-muted' : ''">{{ track.title }}</span>
          <span class="truncate text-xs text-muted">{{ track.artist || t('common.unknownArtist') }} · {{ duration(track.duration) }}</span>
        </button>
        <button type="button" class="grid size-9 place-items-center text-subtle hover:text-ink disabled:opacity-30" :disabled="i === 0" :aria-label="t('common.moveUp')" @click="player.move(i, i - 1)"><ArrowUp :size="16" /></button>
        <button type="button" class="grid size-9 place-items-center text-subtle hover:text-ink disabled:opacity-30" :disabled="i === player.queue.length - 1" :aria-label="t('common.moveDown')" @click="player.move(i, i + 1)"><ArrowDown :size="16" /></button>
        <button type="button" class="grid size-9 place-items-center text-subtle hover:text-danger" :aria-label="t('common.remove')" @click="player.removeAt(i)"><X :size="16" /></button>
      </li>
    </ol>
  </aside>
</template>
