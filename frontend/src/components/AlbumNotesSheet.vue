<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { FileText, Search } from '@lucide/vue'
import { api, query } from '../api'
import { errorMessage } from '../i18n'
import { useUi } from '../stores/ui'
import BaseModal from './BaseModal.vue'

// Admin: the album's introduction (backend album_notes.py). The eztag album card in its folder,
// or an album found on Bugs/Melon (as eztag's tag search does), or written by hand; looked at and
// edited here before it is saved.
const props = defineProps<{ albumId: number; text: string | null; source: string | null }>()
const emit = defineEmits<{ close: []; saved: [text: string | null, source: string | null] }>()
const { t } = useI18n()
const ui = useUi()

interface Found { provider: 'bugs' | 'melon'; id: string; title: string; artist: string; year: number | null; cover: string; url: string }
const draft = ref(props.text ?? '')
const source = ref(props.source ?? 'manual')
const q = ref('')
const items = ref<Found[]>([])
const searching = ref(false)
const searched = ref(false)
const loading = ref('') // the result being fetched
const saving = ref(false)

async function search(text?: string) {
  searching.value = true
  try {
    const r = await api<{ q: string; items: Found[] }>(`/admin/albums/${props.albumId}/notes/search${query({ q: text })}`)
    q.value = r.q
    items.value = r.items
    searched.value = true
  } catch (e) {
    ui.notify(errorMessage(e), true)
  } finally {
    searching.value = false
  }
}
onMounted(() => void search())

async function take(x: Found) {
  loading.value = `${x.provider}:${x.id}`
  try {
    const r = await api<{ text: string; source: string }>(`/admin/albums/${props.albumId}/notes/fetch${query({ provider: x.provider, id: x.id })}`)
    if (!r.text) return ui.notify(t('notes.empty'), true)
    draft.value = r.text
    source.value = r.source
  } catch (e) {
    ui.notify(errorMessage(e), true)
  } finally {
    loading.value = ''
  }
}
async function report() {
  try {
    const r = await api<{ text: string; source: string }>(`/admin/albums/${props.albumId}/notes/report`, { method: 'POST' })
    draft.value = r.text
    source.value = r.source
  } catch (e) {
    ui.notify(errorMessage(e), true)
  }
}
async function save() {
  saving.value = true
  try {
    const r = await api<{ description: string | null; description_source: string | null }>(`/admin/albums/${props.albumId}/notes`, {
      method: 'PUT', body: { text: draft.value, source: draft.value === props.text ? (props.source ?? 'manual') : source.value },
    })
    emit('saved', r.description, r.description_source)
    ui.notify(t('notes.saved'))
    emit('close')
  } catch (e) {
    ui.notify(errorMessage(e), true)
  } finally {
    saving.value = false
  }
}
function typed() {
  if (!source.value.startsWith('manual')) source.value = 'manual'
}
const provider = (s: string) => t(`notes.from_${s.split(':')[0]}`)
</script>

<template>
  <BaseModal :title="t('notes.title')" @close="emit('close')">
    <div class="flex flex-col gap-5">
      <section class="flex flex-col gap-2">
        <div class="flex items-center justify-between gap-2">
          <h3 class="font-medium">{{ t('notes.text') }}</h3>
          <span v-if="draft" class="text-[12px] text-muted">{{ provider(source) }}</span>
        </div>
        <textarea v-model="draft" rows="7" maxlength="20000" class="w-full rounded-2xl bg-surface p-3.5 text-[14px] leading-relaxed outline-none focus:ring-2 focus:ring-ink" :placeholder="t('notes.placeholder')" @input="typed" />
        <div class="flex flex-wrap gap-2">
          <button type="button" class="h-10 rounded-full bg-ink px-5 text-[14px] text-on-ink disabled:opacity-50" :disabled="saving" @click="save">{{ t('common.save') }}</button>
          <button type="button" class="flex h-10 items-center gap-1.5 rounded-full border border-line-strong px-4 text-[14px]" @click="report"><FileText :size="16" :stroke-width="1.5" />{{ t('notes.report') }}</button>
        </div>
      </section>

      <section class="flex flex-col gap-2.5">
        <h3 class="font-medium">{{ t('notes.search') }}</h3>
        <form class="flex h-11 items-center gap-2 rounded-full bg-surface px-4" @submit.prevent="search(q)">
          <Search :size="18" :stroke-width="1.4" class="text-muted" />
          <input v-model="q" type="search" enterkeyhint="search" :aria-label="t('notes.search')" class="min-w-0 flex-1 bg-transparent text-[15px] outline-none" />
        </form>
        <p v-if="searching" class="text-[14px] font-light text-muted">{{ t('common.loading') }}</p>
        <p v-else-if="searched && !items.length" class="text-[14px] font-light text-muted">{{ t('notes.noResults') }}</p>
        <button
          v-for="x in items"
          :key="`${x.provider}:${x.id}`"
          type="button"
          class="flex items-center gap-3 rounded-xl p-1.5 text-left hover:bg-surface disabled:opacity-50"
          :disabled="!!loading"
          @click="take(x)"
        >
          <img v-if="x.cover" :src="x.cover" alt="" referrerpolicy="no-referrer" loading="lazy" class="size-12 flex-none rounded-md bg-surface object-cover" />
          <span v-else class="size-12 flex-none rounded-md bg-surface" />
          <span class="flex min-w-0 flex-1 flex-col">
            <span class="truncate text-[15px]">{{ x.title }}</span>
            <span class="truncate text-[13px] font-light text-muted">{{ x.artist }}<template v-if="x.year"> · {{ x.year }}</template></span>
          </span>
          <span class="flex-none rounded-full px-2 py-0.5 text-[11px] font-medium" :class="x.provider === 'melon' ? 'bg-[#00cd3c]/15 text-[#00a030]' : 'bg-[#ff3b28]/12 text-[#e0301e]'">
            {{ loading === `${x.provider}:${x.id}` ? t('common.loading') : t(`notes.from_${x.provider}`) }}
          </span>
        </button>
        <p class="text-[12px] font-light text-muted">{{ t('notes.help') }}</p>
      </section>
    </div>
  </BaseModal>
</template>
