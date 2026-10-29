<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ChevronRight } from '@lucide/vue'
import { api } from '../api'
import { errorMessage } from '../i18n'
import type { CollectionsHome } from '../types'
import BannerCarousel from '../components/BannerCarousel.vue'
import ChartGrid from '../components/ChartGrid.vue'
import PageHeader from '../components/PageHeader.vue'

// Charts and themes: featured banners, then a row per chart source, today's themes,
// a row per theme category and what came in lately.
const { t } = useI18n()
const home = ref<CollectionsHome | null>(null)
const error = ref('')

onMounted(async () => {
  try {
    home.value = await api<CollectionsHome>('/collections/home')
  } catch (e) {
    error.value = errorMessage(e)
  }
})
</script>

<template>
  <div class="flex flex-col gap-8">
    <PageHeader :title="t('charts.title')" />
    <p v-if="error" class="font-light text-muted">{{ error }}</p>
    <template v-else-if="home">
      <p v-if="!home.hero.length" class="font-light text-muted">{{ t('charts.empty') }}</p>
      <BannerCarousel v-else :items="home.hero" />

      <section v-for="s in home.sources" :key="`s-${s.source}`" class="flex flex-col gap-3.5">
        <RouterLink :to="{ name: 'chart-list', query: { kind: 'chart', source: s.source || undefined } }" class="flex items-center gap-1 text-[22px] font-bold">
          {{ s.source ? t('charts.sourceRow', { source: s.source }) : t('charts.charts') }}
          <ChevronRight :size="22" :stroke-width="1.6" />
        </RouterLink>
        <ChartGrid :charts="s.items" row />
      </section>

      <section v-if="home.picks.length" class="flex flex-col gap-3.5">
        <RouterLink :to="{ name: 'chart-list', query: { kind: 'theme' } }" class="flex items-center gap-1 text-[22px] font-bold">
          {{ t('charts.picks') }} <ChevronRight :size="22" :stroke-width="1.6" />
        </RouterLink>
        <ChartGrid :charts="home.picks" row />
      </section>

      <section v-for="c in home.categories" :key="`c-${c.category}`" class="flex flex-col gap-3.5">
        <RouterLink :to="{ name: 'chart-list', query: { kind: 'theme', source: c.category || undefined } }" class="flex items-center gap-1 text-[22px] font-bold">
          {{ c.category || t('charts.themes') }} <ChevronRight :size="22" :stroke-width="1.6" />
        </RouterLink>
        <ChartGrid :charts="c.items" row />
      </section>

      <section v-if="home.recent.length" class="flex flex-col gap-3.5">
        <h2 class="text-[22px] font-bold">{{ t('charts.recent') }}</h2>
        <ChartGrid :charts="home.recent" row />
      </section>
    </template>
  </div>
</template>
