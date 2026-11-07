<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { Bell } from '@lucide/vue'
import { news } from '../news'

// The bell: to the news page, with how many things were added since this person last looked.
const { t } = useI18n()
</script>

<template>
  <RouterLink
    to="/news"
    class="relative grid size-10 flex-none place-items-center rounded-full bg-surface hover:bg-surface-2"
    :aria-label="news?.total ? t('news.bellNew', { n: news.total }) : t('news.title')"
    :title="news?.total ? t('news.bellNew', { n: news.total }) : t('news.title')"
  >
    <Bell :size="19" :stroke-width="1.6" />
    <span
      v-if="news?.total"
      class="absolute -right-1 -top-1 grid h-[18px] min-w-[18px] place-items-center rounded-full bg-accent px-1 text-[11px] font-medium leading-none text-white"
      aria-hidden="true"
    >{{ news.total > 99 ? '99+' : news.total }}</span>
  </RouterLink>
</template>
