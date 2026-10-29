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
  <div class="fixed inset-0 z-[60] flex justify-end bg-black/20" @click.self="ui.queueOpen = false">
    <aside :aria-label="t('player.queue')" class="pt-safe pb-safe flex h-full w-full max-w-sm flex-col bg-bg shadow-2xl">
      <div class="flex items-center justify-between px-5 py-3">
        <h2 class="text-2xl font-bold">{{ t('player.queue') }}</h2>
        <div class="flex items-center gap-1">
          <button
            v-if="player.queue.length > player.index + 1"
            type="button"
            class="h-9 rounded-full border border-line-strong px-3 text-[13px]"
            @click="player.clearUpcoming()"
          >
            {{ t('player.clearQueue') }}
          </button>
          <button type="button" class="grid size-11 place-items-center" :aria-label="t('common.close')" @click="ui.queueOpen = false">
            <X :size="22" :stroke-width="1.4" />
          </button>
        </div>
      </div>
      <p v-if="!player.queue.length" class="px-5 text-[15px] font-light text-muted">{{ t('player.queueEmpty') }}</p>
      <ol class="flex-1 overflow-y-auto px-2 pb-4">
        <li
          v-for="(track, i) in player.queue"
          :key="`${track.id}-${i}`"
          class="flex items-center gap-1 rounded-xl px-2"
          :class="i === player.index ? 'bg-accent-soft' : ''"
        >
          <button type="button" class="flex min-w-0 flex-1 flex-col py-2.5 text-left" @click="player.jump(i)">
            <span class="truncate text-[15px]" :class="i === player.index ? 'font-medium text-accent' : i < player.index ? 'text-muted' : ''">{{ track.title }}</span>
            <span class="truncate text-[13px] font-light text-muted">{{ track.artist || t('common.unknownArtist') }} · {{ duration(track.duration) }}</span>
          </button>
          <button type="button" class="grid size-10 place-items-center text-muted disabled:opacity-30" :disabled="i === 0" :aria-label="t('common.moveUp')" @click="player.move(i, i - 1)"><ArrowUp :size="16" /></button>
          <button type="button" class="grid size-10 place-items-center text-muted disabled:opacity-30" :disabled="i === player.queue.length - 1" :aria-label="t('common.moveDown')" @click="player.move(i, i + 1)"><ArrowDown :size="16" /></button>
          <button type="button" class="grid size-10 place-items-center text-muted hover:text-danger" :aria-label="t('common.remove')" @click="player.removeAt(i)"><X :size="16" /></button>
        </li>
      </ol>
    </aside>
  </div>
</template>
