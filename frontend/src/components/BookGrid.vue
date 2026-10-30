<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { longDuration } from '../format'
import type { Book } from '../types'
import BookCover from './BookCover.vue'

defineProps<{ books: Book[]; row?: boolean }>()
const { t } = useI18n()

const left = (b: Book) => (b.progress ? Math.max(0, b.duration - b.progress.position) : b.duration)
const pct = (b: Book) => (b.progress && b.duration ? Math.min(100, (b.progress.position / b.duration) * 100) : 0)
</script>

<template>
  <div
    :class="
      row
        ? '-mr-5 flex gap-3 overflow-x-auto pb-2 pr-5 [scrollbar-width:none] md:mr-0 md:pr-0'
        : 'grid grid-cols-2 gap-x-3 gap-y-6 sm:grid-cols-[repeat(auto-fill,minmax(150px,1fr))] sm:gap-x-5'
    "
  >
    <RouterLink
      v-for="b in books"
      :key="b.id"
      :to="{ name: 'book', params: { id: b.id } }"
      class="flex min-w-0 flex-col gap-2"
      :class="row ? 'w-[124px] flex-none sm:w-36' : ''"
    >
      <BookCover :book-id="b.id" :has-cover="b.has_cover" :version="b.cover_v">
        <span v-if="b.progress && !b.progress.finished" class="absolute inset-x-0 bottom-0 h-1 bg-black/20">
          <span class="block h-full bg-accent" :style="{ width: `${pct(b)}%` }" />
        </span>
      </BookCover>
      <span class="flex min-w-0 flex-col">
        <span class="line-clamp-2 text-[15px] leading-snug">{{ b.title }}</span>
        <span class="truncate text-[13px] font-light text-muted">{{ b.authors || t('books.unknownAuthor') }}</span>
        <span class="truncate text-[12px] font-light text-subtle">
          <template v-if="b.progress?.finished">{{ t('books.finished') }}</template>
          <template v-else-if="b.progress">{{ t('books.left', { time: longDuration(left(b)) }) }}</template>
          <template v-else>{{ longDuration(b.duration) }}</template>
        </span>
      </span>
    </RouterLink>
  </div>
</template>
