<script setup lang="ts">
import { useI18n } from 'vue-i18n'

// "More" under a list that comes page by page. `small`: inside a sheet.
defineProps<{ loading?: boolean; small?: boolean }>()
const { t } = useI18n()
</script>

<template>
  <button
    type="button"
    class="mx-auto self-center rounded-full border border-line-strong disabled:opacity-40"
    :class="small ? 'h-10 px-5 text-[14px]' : 'h-11 px-6 text-[15px]'"
    :disabled="loading"
  >
    {{ loading ? t('common.loading') : t('common.loadMore') }}
  </button>
</template>
