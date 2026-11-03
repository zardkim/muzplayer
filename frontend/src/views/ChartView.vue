<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ListMusic, Sparkles } from '@lucide/vue'
import { api } from '../api'
import { appConfig } from '../config'
import { errorMessage } from '../i18n'
import { useAuth } from '../stores/auth'
import { useUi } from '../stores/ui'
import type { ChartDetail, CollectionBanner } from '../types'
import BannerCard from '../components/BannerCard.vue'
import BannerSheet from '../components/BannerSheet.vue'
import PlayActions from '../components/PlayActions.vue'
import TrackList from '../components/TrackList.vue'

const props = defineProps<{ id: string }>()
const { t } = useI18n()
const auth = useAuth()
const ui = useUi()
const chart = ref<ChartDetail | null>(null)
const error = ref('')
const editing = ref(false)

onMounted(async () => {
  try {
    chart.value = await api<ChartDetail>(`/charts/${props.id}`)
  } catch (e) {
    error.value = errorMessage(e)
  }
})

// admin: the chart's songs as a playlist for everyone (charts & themes page, home), or the one made already
const router = useRouter()
const making = ref(false)
async function makeShared() {
  if (!chart.value || making.value) return
  making.value = true
  try {
    const r = await api<{ id: number }>(`/charts/${chart.value.id}/shared-playlist`, { method: 'POST', body: {} })
    ui.notify(t('shared.made'))
    router.push({ name: 'playlist', params: { id: r.id } })
  } catch (e) {
    ui.notify(errorMessage(e), true)
  } finally {
    making.value = false
  }
}

function applied(banner: CollectionBanner | null) {
  if (chart.value) chart.value.banner = banner
  editing.value = false
}
</script>

<template>
  <p v-if="error" class="font-light text-muted">{{ error }}</p>
  <div v-else-if="chart" class="flex flex-col gap-5">
    <BannerCard :chart="chart" :link="false" size="header">
      <button
        v-if="appConfig.aiBanners && auth.user?.is_admin"
        type="button"
        class="absolute right-3 top-3 flex h-9 items-center gap-1.5 rounded-full bg-black/45 px-3 text-[13px] text-white backdrop-blur-sm"
        @click="editing = true"
      >
        <Sparkles :size="15" :stroke-width="1.8" />{{ t('banner.button') }}
      </button>
    </BannerCard>
    <h1 class="sr-only">{{ chart.title }}</h1>
    <div class="flex flex-wrap gap-2">
      <PlayActions :tracks="chart.tracks" />
      <button type="button" class="h-[38px] rounded-full border border-line-strong px-4 text-[15px]" @click="ui.playlistPicker = chart.tracks">{{ t('charts.copyToPlaylist') }}</button>
      <RouterLink v-if="chart.shared_playlist_id" :to="{ name: 'playlist', params: { id: chart.shared_playlist_id } }" class="flex h-[38px] items-center gap-1.5 rounded-full border border-line-strong px-4 text-[15px]">
        <ListMusic :size="16" :stroke-width="1.5" />{{ t('shared.open') }}
      </RouterLink>
      <button v-else-if="auth.user?.is_admin" type="button" class="flex h-[38px] items-center gap-1.5 rounded-full border border-line-strong px-4 text-[15px] disabled:opacity-40" :disabled="making" @click="makeShared">
        <ListMusic :size="16" :stroke-width="1.5" />{{ t('shared.make') }}
      </button>
    </div>
    <TrackList :tracks="chart.tracks" :ranked="chart.tracks.some((tr) => tr.chart_position != null)" />
    <BannerSheet v-if="editing" :chart="chart" @close="editing = false" @applied="applied" />
  </div>
</template>
