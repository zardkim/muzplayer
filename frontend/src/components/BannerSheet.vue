<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api'
import { errorMessage } from '../i18n'
import { useUi } from '../stores/ui'
import type { Chart, CollectionBanner } from '../types'
import BannerCard from './BannerCard.vue'
import BaseModal from './BaseModal.vue'

// Admin: make a banner with AI, refine it in words, apply it to this collection (or, for a
// chart, to every week of its source). Each "make"/"edit" is one paid image request.
const props = defineProps<{ chart: Chart }>()
const emit = defineEmits<{ close: []; applied: [banner: CollectionBanner | null] }>()
const { t } = useI18n()
const ui = useUi()

const prompt = ref('')
const useCovers = ref(true)
const instruction = ref('')
const candidate = ref<{ token: string; url: string } | null>(null)
const usedPrompt = ref('')
const busy = ref<'make' | 'edit' | 'apply' | 'reset' | null>(null)
const error = ref('')
const scope = ref<'collection' | 'source'>('collection')
const canShare = computed(() => props.chart.kind === 'chart' && !!props.chart.source)
const ownAi = computed(() => (props.chart.banner?.kind === 'ai' ? props.chart.banner : null))

onMounted(async () => {
  prompt.value = (await api<{ prompt: string }>(`/admin/banners/prompt?chart_id=${props.chart.id}`)).prompt
})

async function generate(edit: boolean) {
  busy.value = edit ? 'edit' : 'make'
  error.value = ''
  try {
    const body = edit
      ? {
          chart_id: props.chart.id,
          instruction: instruction.value,
          edit_candidate: candidate.value?.token ?? null,
          edit_banner: candidate.value ? null : ownAi.value?.id ?? null,
        }
      : { chart_id: props.chart.id, prompt: prompt.value, use_covers: useCovers.value }
    const r = await api<{ job: string; prompt: string }>('/admin/banners/generate', { method: 'POST', body })
    // the image is made in the background (10–60 s): poll rather than hold one long request
    let job: { status: string; candidate: string | null; url: string | null; error: string | null }
    do {
      await new Promise((ok) => setTimeout(ok, 2000))
      job = await api(`/admin/banners/jobs/${r.job}`)
    } while (job.status === 'running')
    if (job.status !== 'done' || !job.candidate || !job.url) throw { code: job.error ?? 'ai_bad_response' }
    candidate.value = { token: job.candidate, url: job.url }
    usedPrompt.value = edit ? `${usedPrompt.value || prompt.value}\n\n[edit] ${instruction.value}` : r.prompt
    if (edit) instruction.value = ''
  } catch (e) {
    error.value = errorMessage(e)
  } finally {
    busy.value = null
  }
}

async function apply() {
  if (!candidate.value) return
  busy.value = 'apply'
  try {
    const r = await api<{ banner: CollectionBanner | null }>('/admin/banners', {
      method: 'POST',
      body: { chart_id: props.chart.id, candidate: candidate.value.token, scope: scope.value, prompt: usedPrompt.value },
    })
    // a source-wide banner stays hidden behind this week's own one
    ui.notify(scope.value === 'source' && r.banner?.scope === 'collection' ? t('banner.appliedShadowed') : t('banner.applied'))
    ui.libraryCheckedAt = 0 // kept chart/theme lists pick the new banner up on the next page
    emit('applied', r.banner)
  } catch (e) {
    error.value = errorMessage(e)
  } finally {
    busy.value = null
  }
}

async function reset() {
  if (!props.chart.banner?.id) return
  busy.value = 'reset'
  try {
    const r = await api<{ banner: CollectionBanner | null }>(`/admin/banners/${props.chart.banner.id}?chart_id=${props.chart.id}`, { method: 'DELETE' })
    ui.notify(t('banner.resetDone'))
    ui.libraryCheckedAt = 0
    emit('applied', r.banner)
  } catch (e) {
    error.value = errorMessage(e)
  } finally {
    busy.value = null
  }
}
</script>

<template>
  <BaseModal :title="t('banner.title')" @close="emit('close')">
    <div class="flex flex-col gap-4">
      <BannerCard :chart="chart" :image="candidate ? candidate.url : undefined" :link="false" size="small" />
      <p v-if="busy === 'make' || busy === 'edit'" class="text-center text-[14px] text-muted" role="status">
        <span class="inline-block size-3 animate-pulse rounded-full bg-accent align-middle" /> {{ t('banner.working') }}
      </p>
      <p v-if="error" class="text-[14px] text-danger" role="alert">{{ error }}</p>

      <!-- refine the candidate (or the current AI banner) in words -->
      <div v-if="candidate || ownAi" class="flex flex-col gap-2">
        <label for="banner-edit" class="text-[14px] font-medium">{{ candidate ? t('banner.editCandidate') : t('banner.editCurrent') }}</label>
        <div class="flex gap-2">
          <input
            id="banner-edit"
            v-model="instruction"
            type="text"
            maxlength="2000"
            class="h-11 min-w-0 flex-1 rounded-full border border-line-strong bg-bg px-4 text-[15px]"
            :placeholder="t('banner.editPlaceholder')"
            @keydown.enter.prevent="instruction.trim() && !busy && generate(true)"
          />
          <button type="button" class="h-11 flex-none rounded-full border border-line-strong px-4 text-[15px] disabled:opacity-40" :disabled="!instruction.trim() || !!busy" @click="generate(true)">
            {{ t('banner.edit') }}
          </button>
        </div>
      </div>

      <template v-if="candidate">
        <fieldset v-if="canShare" class="flex flex-col gap-1.5">
          <legend class="mb-1 text-[14px] font-medium">{{ t('banner.scope') }}</legend>
          <label class="flex items-center gap-2 text-[15px]"><input v-model="scope" type="radio" value="collection" /> {{ t('banner.scopeCollection') }}</label>
          <label class="flex items-center gap-2 text-[15px]"><input v-model="scope" type="radio" value="source" /> {{ t('banner.scopeSource', { source: chart.source }) }}</label>
        </fieldset>
        <div class="flex gap-2">
          <button type="button" class="h-11 flex-1 rounded-full bg-ink text-[15px] text-on-ink disabled:opacity-40" :disabled="!!busy" @click="apply">{{ t('banner.apply') }}</button>
          <button type="button" class="h-11 flex-1 rounded-full border border-line-strong text-[15px] disabled:opacity-40" :disabled="!!busy" @click="generate(false)">{{ t('banner.again') }}</button>
        </div>
      </template>

      <details :open="!candidate" class="flex flex-col gap-2">
        <summary class="cursor-pointer text-[14px] font-medium">{{ t('banner.prompt') }}</summary>
        <textarea
          v-model="prompt"
          rows="8"
          maxlength="4000"
          class="mt-2 w-full rounded-2xl border border-line-strong bg-bg p-3 text-[14px] leading-relaxed"
          :aria-label="t('banner.prompt')"
        />
        <label class="mt-2 flex items-center gap-2 text-[14px]">
          <input v-model="useCovers" type="checkbox" /> {{ t('banner.useCovers') }}
        </label>
        <button v-if="!candidate" type="button" class="mt-3 h-11 w-full rounded-full bg-ink text-[15px] text-on-ink disabled:opacity-40" :disabled="!!busy || !prompt.trim()" @click="generate(false)">
          {{ t('banner.make') }}
        </button>
      </details>

      <p class="text-[12px] leading-relaxed text-muted">{{ t('banner.costNote') }}</p>
      <button v-if="ownAi" type="button" class="text-left text-[14px] text-accent underline disabled:opacity-40" :disabled="!!busy" @click="reset">
        {{ ownAi.scope === 'source' ? t('banner.resetSource', { source: chart.source }) : t('banner.reset') }}
      </button>
    </div>
  </BaseModal>
</template>
