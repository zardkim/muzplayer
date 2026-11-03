<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { EllipsisVertical } from '@lucide/vue'
import { api } from '../api'
import { duration, longDuration } from '../format'
import { errorMessage } from '../i18n'
import { usePlayer } from '../stores/player'
import { useUi } from '../stores/ui'
import type { BookDetail } from '../types'
import BookCover from '../components/BookCover.vue'
import PlayerIcons from '../components/PlayerIcons.vue'
import SectionTitle from '../components/SectionTitle.vue'
import Marquee from '../components/Marquee.vue'

const props = defineProps<{ id: string }>()
const { t } = useI18n()
const player = usePlayer()
const ui = useUi()
const book = ref<BookDetail | null>(null)
const notFound = ref(false)
const expanded = ref(false)
const menu = ref(false)

onMounted(async () => {
  try {
    book.value = await api<BookDetail>(`/books/${props.id}`)
    player.syncBook(book.value) // paused here but listened on another device since
  } catch {
    notFound.value = true
  }
})

// the player's copy has the freshest position while this book is open there
const isOpen = computed(() => player.mode === 'book' && player.book?.id === book.value?.id)
const progress = computed(() => (isOpen.value ? player.book?.progress : book.value?.progress) ?? null)
const position = computed(() => (isOpen.value ? player.bookPos : (progress.value?.position ?? 0)))
const started = computed(() => !!progress.value && !progress.value.finished && position.value > 0)
const pct = computed(() => (book.value?.duration ? Math.min(100, (position.value / book.value.duration) * 100) : 0))
const current = computed(() => (isOpen.value ? player.chapterIndex : -1))
// "more" only when the description would be cut at three lines
const longDescription = computed(() => {
  const d = book.value?.description ?? ''
  return d.length > 160 || d.split('\n').length > 3
})

function play() {
  if (!book.value) return
  if (isOpen.value) return player.toggle()
  player.playBook(book.value)
}

function playChapter(start: number) {
  if (!book.value) return
  if (isOpen.value) player.seekBook(start, true)
  else player.playBook(book.value, start)
}

async function setFinished(finished: boolean) {
  menu.value = false
  if (!book.value) return
  try {
    if (finished) {
      const p = await api<BookDetail['progress']>(`/books/${book.value.id}/progress`, {
        method: 'PUT',
        body: { position: book.value.duration, finished: true },
      })
      book.value.progress = p
    } else {
      if (!confirm(t('books.restartConfirm'))) return
      await api(`/books/${book.value.id}/progress`, { method: 'DELETE' })
      book.value.progress = null
    }
    if (isOpen.value && player.book) {
      player.book.progress = book.value.progress
      // move the player too, or its next save would undo this
      player.seekBook(finished ? book.value.duration : 0, false)
    }
  } catch (e) {
    ui.notify(errorMessage(e), true)
  }
}
</script>

<template>
  <p v-if="notFound" class="font-light text-muted">{{ t('errors.not_found') }}</p>
  <div v-else-if="book" class="flex flex-col gap-7">
    <div class="flex flex-col gap-6 md:flex-row md:items-end">
      <BookCover :book-id="book.id" :has-cover="book.has_cover" :version="book.cover_v" size="large" rounded="rounded-xl" class="mx-auto w-[min(56%,240px)] flex-none shadow-[0_8px_30px_rgba(17,17,19,0.14)] md:mx-0 md:w-60" />
      <div class="flex min-w-0 flex-col gap-1.5">
        <Marquee as="h1" :text="book.title" class="text-[28px] font-extrabold leading-tight tracking-tight md:text-[34px]" />
        <p v-if="book.subtitle" class="text-[17px] font-light text-muted">{{ book.subtitle }}</p>
        <p class="text-[15px]">
          <RouterLink v-if="book.authors" :to="{ name: 'books', query: { author: book.authors } }" class="hover:underline">{{ book.authors }}</RouterLink>
          <span v-else class="text-muted">{{ t('books.unknownAuthor') }}</span>
        </p>
        <p v-if="book.narrators" class="text-[14px] font-light text-muted">{{ t('books.narratedBy', { name: book.narrators }) }}</p>
        <p v-if="book.series" class="text-[14px]">
          <RouterLink :to="{ name: 'books', query: { series: book.series } }" class="text-accent hover:underline">
            {{ book.series_seq ? t('books.seriesSeq', { name: book.series, n: book.series_seq }) : book.series }}
          </RouterLink>
        </p>
        <p class="text-[13px] font-light text-muted">
          {{ longDuration(book.duration) }}<template v-if="book.chapters.length"> · {{ t('books.chapterCount', { n: book.chapters.length }) }}</template><template v-if="book.published_year"> · {{ book.published_year }}</template>
        </p>
      </div>
    </div>

    <div class="flex flex-col gap-2">
      <div v-if="progress" class="flex items-center gap-3 text-[13px] text-muted">
        <span class="h-1 flex-1 overflow-hidden rounded-full bg-line"><span class="block h-full bg-accent" :style="{ width: `${progress.finished ? 100 : pct}%` }" /></span>
        <span>{{ progress.finished ? t('books.finished') : t('books.left', { time: longDuration(book.duration - position) }) }}</span>
      </div>
      <div class="flex items-center gap-2.5">
        <button type="button" class="flex h-12 flex-1 items-center justify-center gap-2 rounded-full bg-ink px-6 text-[16px] text-on-ink md:flex-none" @click="play">
          <PlayerIcons :name="isOpen && player.playing ? 'pause' : 'play'" :size="20" :stroke="1.8" />
          <template v-if="isOpen && player.playing">{{ t('player.pause') }}</template>
          <template v-else-if="started">{{ t('books.resume', { time: duration(position) }) }}</template>
          <template v-else>{{ t('books.listen') }}</template>
        </button>
        <div class="relative">
          <button type="button" class="grid size-12 place-items-center rounded-full border border-line-strong" :aria-label="t('common.moreActions')" @click="menu = !menu">
            <EllipsisVertical :size="20" :stroke-width="1.4" />
          </button>
          <div v-if="menu" class="absolute right-0 top-14 z-10 flex w-56 flex-col overflow-hidden rounded-2xl border border-line bg-bg py-1.5 text-[15px] shadow-xl">
            <button v-if="!progress?.finished" type="button" class="px-4 py-3 text-left hover:bg-surface" @click="setFinished(true)">{{ t('books.markFinished') }}</button>
            <button v-if="progress" type="button" class="px-4 py-3 text-left hover:bg-surface" @click="setFinished(false)">{{ t('books.restart') }}</button>
            <span v-if="!progress" class="px-4 py-3 text-muted">{{ t('books.notStarted') }}</span>
          </div>
        </div>
      </div>
    </div>

    <section v-if="book.description" class="flex flex-col gap-1.5">
      <p class="whitespace-pre-line text-[15px] font-light leading-relaxed" :class="expanded || !longDescription ? '' : 'line-clamp-3'">{{ book.description }}</p>
      <button v-if="longDescription" type="button" class="self-start text-[14px] text-accent" @click="expanded = !expanded">{{ expanded ? t('books.less') : t('books.more') }}</button>
    </section>

    <section v-if="book.chapters.length" class="flex flex-col gap-2">
      <SectionTitle :title="t('books.chapters')" />
      <ol class="flex flex-col">
        <li v-for="(c, i) in book.chapters" :key="i" class="border-b border-surface last:border-0">
          <button
            type="button"
            class="flex w-full items-center gap-3 py-3 text-left"
            :class="i === current ? 'text-accent' : ''"
            :aria-current="i === current ? 'true' : undefined"
            @click="playChapter(c.start)"
          >
            <span class="w-8 flex-none font-display text-[13px] text-muted">{{ i + 1 }}</span>
            <span class="min-w-0 flex-1 truncate text-[16px]">{{ c.title }}</span>
            <span class="font-display text-[13px] text-muted">{{ duration(c.end - c.start) }}</span>
          </button>
        </li>
      </ol>
    </section>
  </div>
</template>
