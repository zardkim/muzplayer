<script setup lang="ts">
import { computed, onActivated, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { RefreshCw } from '@lucide/vue'
import { api } from '../api'
import { errorMessage } from '../i18n'
import { useLibrary } from '../stores/library'
import { useUi } from '../stores/ui'
import type { Track } from '../types'
import PageHeader from '../components/PageHeader.vue'
import PlayActions from '../components/PlayActions.vue'
import TrackList from '../components/TrackList.vue'

// One mix (random 100, on repeat, ...). The list is worked out when the page opens and stays as
// it is while playing and when coming back to the page (kept alive in App.vue); "shuffle again"
// asks for a new one. Mixes that follow plays (on repeat, most played) refresh on coming back.
const props = defineProps<{ mixKey: string }>()
const { t } = useI18n()
const library = useLibrary()
const ui = useUi()
const tracks = ref<Track[]>([])
const loaded = ref(false)
const error = ref('')

const RANDOM = ['random', 'top-rated', 'unplayed', '1990s', '2000s', '2010s', '2020s']
const random = computed(() => RANDOM.includes(props.mixKey))
const name = computed(() => t(`mixes.names.${props.mixKey}`))
const desc = computed(() =>
  /^\d{4}s$/.test(props.mixKey) ? t('mixes.desc.decade', { decade: name.value }) : t(`mixes.desc.${props.mixKey}`),
)

async function load() {
  try {
    tracks.value = (await api<{ tracks: Track[] }>(`/mixes/${props.mixKey}`)).tracks
  } catch (e) {
    error.value = errorMessage(e)
  } finally {
    loaded.value = true
  }
}
onMounted(load)
let first = true
onActivated(() => {
  if (!first && !random.value) load()
  first = false
})

// keep this exact list (in this order) as an ordinary playlist
async function save() {
  try {
    const p = await library.createPlaylist(`${name.value} ${new Date().toLocaleDateString()}`)
    await library.addToPlaylist(p.id, tracks.value)
    ui.notify(t('common.saved'))
  } catch (e) {
    ui.notify(errorMessage(e), true)
  }
}
</script>

<template>
  <p v-if="error" class="font-light text-muted">{{ error }}</p>
  <div v-else class="flex flex-col gap-5">
    <PageHeader :title="name" :sub="desc" />
    <div class="flex flex-wrap gap-2">
      <PlayActions :tracks="tracks" />
      <button v-if="random" type="button" class="flex h-[38px] items-center gap-1.5 rounded-full border border-line-strong px-4 text-[15px]" @click="load">
        <RefreshCw :size="15" :stroke-width="1.6" />{{ t('common.reshuffle') }}
      </button>
      <button type="button" class="h-[38px] rounded-full border border-line-strong px-4 text-[15px] disabled:opacity-40" :disabled="!tracks.length" @click="save">{{ t('common.saveAsPlaylist') }}</button>
    </div>
    <p v-if="loaded && !tracks.length" class="font-light text-muted">{{ t('common.empty') }}</p>
    <TrackList :tracks="tracks" />
  </div>
</template>
