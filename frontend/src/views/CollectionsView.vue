<script setup lang="ts">
import { chartSource } from '../format'
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api'
import { errorMessage } from '../i18n'
import type { CollectionsHome } from '../types'
import BannerCarousel from '../components/BannerCarousel.vue'
import ChartGrid from '../components/ChartGrid.vue'
import PageHeader from '../components/PageHeader.vue'
import SharedPlaylists from '../components/SharedPlaylists.vue'
import SectionTitle from '../components/SectionTitle.vue'

// Charts and themes: featured banners (what came in lately first), what came in lately, then
// a row per chart source, today's themes and a row per theme category.
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

      <section v-if="home.recent.length" class="flex flex-col gap-3.5">
        <SectionTitle :title="t('charts.recent')" />
        <ChartGrid :charts="home.recent" row />
      </section>

      <!-- the playlists made from charts and themes for everyone -->
      <SharedPlaylists />

      <section v-for="s in home.sources" :key="`s-${s.source}`" class="flex flex-col gap-3.5">
        <SectionTitle
          :title="s.source && chartSource(s.source) ? t('charts.sourceRow', { source: chartSource(s.source) }) : t('charts.charts')"
          :source="s.source"
          :to="{ name: 'chart-list', query: { kind: 'chart', source: s.source || undefined } }"
        />
        <ChartGrid :charts="s.items" row />
      </section>

      <section v-if="home.picks.length" class="flex flex-col gap-3.5">
        <SectionTitle :title="t('charts.picks')" :to="{ name: 'chart-list', query: { kind: 'theme' } }" />
        <ChartGrid :charts="home.picks" row />
      </section>

      <section v-for="c in home.categories" :key="`c-${c.category}`" class="flex flex-col gap-3.5">
        <SectionTitle :title="c.category || t('charts.themes')" :to="{ name: 'chart-list', query: { kind: 'theme', source: c.category || undefined } }" />
        <ChartGrid :charts="c.items" row />
      </section>

    </template>
  </div>
</template>
