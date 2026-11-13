<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Search, X } from '@lucide/vue'
import { api, query } from '../api'
import { useAuth } from '../stores/auth'
import type { Book, Page } from '../types'
import BookGrid from '../components/BookGrid.vue'
import PageHeader from '../components/PageHeader.vue'
import LoadMore from '../components/LoadMore.vue'
import SectionTitle from '../components/SectionTitle.vue'

const { t } = useI18n()
const auth = useAuth()
const route = useRoute()
const router = useRouter()
const str = (v: unknown) => (typeof v === 'string' ? v : '')
const q = computed(() => str(route.query.q))
const author = computed(() => str(route.query.author))
const series = computed(() => str(route.query.series))
const sort = computed(() => str(route.query.sort) || 'title')
const filtered = computed(() => !!(q.value || author.value || series.value))

const text = ref(q.value)
const items = ref<Book[]>([])
const total = ref(0)
const listening = ref<Book[]>([])
const recent = ref<Book[]>([])
const loading = ref(false)
const loaded = ref(false)

async function load() {
  loading.value = true
  try {
    const page = await api<Page<Book>>(
      `/books${query({ q: q.value, author: author.value, series: series.value, sort: sort.value, limit: 120, offset: items.value.length })}`,
    )
    items.value.push(...page.items)
    total.value = page.total
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  const extra = filtered.value
    ? []
    : [
        api<{ items: Book[] }>('/books/continue').then((r) => (listening.value = r.items)),
        api<Page<Book>>('/books?sort=recent&limit=12').then((r) => (recent.value = r.items)),
      ]
  await Promise.all([load(), ...extra]).catch(() => {})
  loaded.value = true
})

function submit() {
  router.replace({ query: { ...route.query, q: text.value.trim() || undefined } })
}

const sorts = [
  { key: 'title', label: 'books.sortTitle' },
  { key: 'author', label: 'books.sortAuthor' },
  { key: 'recent', label: 'books.sortRecent' },
]
const chips = computed(() =>
  [
    author.value && { key: 'author', label: t('books.filterAuthor', { name: author.value }) },
    series.value && { key: 'series', label: t('books.filterSeries', { name: series.value }) },
  ].filter((c): c is { key: string; label: string } => !!c),
)
</script>

<template>
  <div class="flex flex-col gap-7">
    <PageHeader :title="t('books.title')" :sub="loaded ? t('books.count', { n: total }) : ''" />

    <!-- phones: wide screens search from the top bar (App.vue) -->
    <form role="search" class="flex h-[50px] md:hidden items-center gap-2.5 rounded-full bg-surface px-[18px]" @submit.prevent="submit">
      <Search :size="22" :stroke-width="1.4" class="text-muted" aria-hidden="true" />
      <label for="book-search" class="sr-only">{{ t('books.searchPlaceholder') }}</label>
      <input id="book-search" v-model="text" type="search" enterkeyhint="search" :placeholder="t('books.searchPlaceholder')" class="min-w-0 flex-1 bg-transparent text-[17px] font-light outline-none placeholder:text-muted" />
    </form>

    <div v-if="chips.length" class="flex flex-wrap gap-2">
      <button
        v-for="c in chips"
        :key="c.key"
        type="button"
        class="flex h-[38px] items-center gap-1.5 rounded-full border border-ink bg-ink px-4 text-[15px] text-on-ink"
        :aria-label="`${c.label} · ${t('books.clearFilter')}`"
        @click="router.replace({ query: { ...route.query, [c.key]: undefined } })"
      >
        {{ c.label }}<X :size="16" :stroke-width="1.8" />
      </button>
    </div>

    <div v-if="loaded && !filtered && !total" class="rounded-2xl bg-surface p-8 text-center">
      <p class="font-medium">{{ t('books.empty') }}</p>
      <p v-if="auth.user?.is_admin" class="mt-2 text-sm">
        <RouterLink to="/admin" class="text-accent underline">{{ t('books.emptyAdmin') }}</RouterLink>
      </p>
    </div>

    <template v-if="!filtered">
      <section v-if="listening.length" class="flex flex-col gap-3.5">
        <SectionTitle :title="t('books.continue')" />
        <BookGrid :books="listening" row />
      </section>
      <section v-if="recent.length" class="flex flex-col gap-3.5">
        <SectionTitle :title="t('books.recent')" />
        <BookGrid :books="recent" row />
      </section>
    </template>

    <section v-if="total" class="flex flex-col gap-3.5">
      <div class="flex flex-wrap items-center justify-between gap-2">
        <SectionTitle v-if="!filtered" :title="t('books.all')" />
        <div v-if="!series" class="-mr-5 flex gap-1 overflow-x-auto pr-5 text-[14px] [scrollbar-width:none]">
          <button
            v-for="s in sorts"
            :key="s.key"
            type="button"
            class="h-8 flex-none rounded-full px-3"
            :class="sort === s.key ? 'bg-surface-2 font-medium' : 'font-light text-muted'"
            @click="router.replace({ query: { ...route.query, sort: s.key } })"
          >
            {{ t(s.label) }}
          </button>
        </div>
      </div>
      <BookGrid :books="items" />
      <LoadMore v-if="items.length < total" auto :loading="loading" @click="load" />
    </section>
    <p v-else-if="loaded && filtered" class="font-light text-muted">{{ t('search.noResults') }}</p>
  </div>
</template>
