<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Search, X } from '@lucide/vue'
import { api, query } from '../api'
import { errorMessage } from '../i18n'
import { useUi } from '../stores/ui'
import BaseModal from './BaseModal.vue'

// Admin: tidy up duplicate artists or genres (backend merge.py). Suggested groups of look-alike
// names, a search to pick any names by hand, and the merges made so far (each can be undone).
const props = defineProps<{ kind: 'artist' | 'genre' }>()
const emit = defineEmits<{ close: []; changed: [] }>()
const { t } = useI18n()
const ui = useUi()

interface Name { id: number; name: string; songs: number }
interface Group { items: Name[]; keep: number; picked: Set<number> }
const groups = ref<Group[]>([])
const merged = ref<{ name: string; target: string }[]>([])
const loaded = ref(false)
const busy = ref(false)

async function load() {
  const r = await api<{ groups: Name[][]; merged: { name: string; target: string }[] }>(`/admin/duplicates/${props.kind}`)
  groups.value = r.groups.map((items) => reactive({ items, keep: items[0].id, picked: new Set(items.map((x) => x.id)) }))
  merged.value = r.merged
  loaded.value = true
}
onMounted(() => load().catch((e) => ui.notify(errorMessage(e), true)))

async function run(keep: number, ids: number[]) {
  busy.value = true
  try {
    const r = await api<{ merged: number }>(`/admin/merge/${props.kind}`, { method: 'POST', body: { keep, ids: ids.filter((i) => i !== keep) } })
    ui.notify(t('merge.done', { n: r.merged }))
    manual.value = []
    await load()
    emit('changed')
  } catch (e) {
    ui.notify(errorMessage(e), true)
  } finally {
    busy.value = false
  }
}
async function undo(name: string) {
  busy.value = true
  try {
    await api(`/admin/merge/${props.kind}${query({ name })}`, { method: 'DELETE' })
    ui.notify(t('merge.undone'))
    await load()
    emit('changed')
  } catch (e) {
    ui.notify(errorMessage(e), true)
  } finally {
    busy.value = false
  }
}
function toggle(g: Group, id: number) {
  if (g.picked.has(id)) g.picked.delete(id)
  else g.picked.add(id)
  if (!g.picked.has(g.keep)) g.picked.add(g.keep) // the kept name is always part of it
}

// ---- by hand: search names, pick two or more ----
const text = ref('')
const found = ref<Name[]>([])
const manual = ref<Name[]>([])
const manualKeep = ref<number | null>(null)
let allGenres: Name[] | null = null
let timer = 0
watch(text, (q) => {
  window.clearTimeout(timer)
  timer = window.setTimeout(() => void searchNames(q.trim()), 250)
})
async function searchNames(q: string) {
  if (!q) return (found.value = [])
  if (props.kind === 'genre') {
    allGenres ??= (await api<{ items: { id: number; name: string; track_count: number }[] }>('/genres')).items.map((g) => ({ id: g.id, name: g.name, songs: g.track_count }))
    found.value = allGenres.filter((g) => g.name.toLowerCase().includes(q.toLowerCase())).slice(0, 20)
  } else {
    const r = await api<{ items: { id: number; name: string; track_count: number }[] }>(`/artists${query({ q, limit: 20 })}`)
    found.value = r.items.map((a) => ({ id: a.id, name: a.name, songs: a.track_count }))
  }
}
function pick(x: Name) {
  if (!manual.value.some((m) => m.id === x.id)) manual.value.push(x)
  if (manualKeep.value === null || !manual.value.some((m) => m.id === manualKeep.value)) manualKeep.value = manual.value[0].id
}
function unpick(id: number) {
  manual.value = manual.value.filter((m) => m.id !== id)
  if (manualKeep.value === id) manualKeep.value = manual.value[0]?.id ?? null
}
const choices = computed(() => found.value.filter((x) => !manual.value.some((m) => m.id === x.id)))
const title = computed(() => t(props.kind === 'artist' ? 'merge.titleArtists' : 'merge.titleGenres'))
const songs = (n: number) => t('common.tracks', n)
</script>

<template>
  <BaseModal :title="title" @close="emit('close')">
    <div class="flex flex-col gap-6">
      <p class="text-[13px] font-light leading-relaxed text-muted">{{ t('merge.intro') }}</p>

      <!-- by hand -->
      <section class="flex flex-col gap-2.5">
        <h3 class="font-medium">{{ t('merge.byHand') }}</h3>
        <label class="flex h-11 items-center gap-2 rounded-full bg-surface px-4">
          <Search :size="18" :stroke-width="1.4" class="text-muted" />
          <span class="sr-only">{{ t('merge.search') }}</span>
          <input v-model="text" type="search" :placeholder="t('merge.search')" class="min-w-0 flex-1 bg-transparent text-[15px] outline-none placeholder:text-muted" />
        </label>
        <div v-if="choices.length" class="flex flex-wrap gap-1.5">
          <button v-for="x in choices" :key="x.id" type="button" class="h-8 rounded-full border border-line-strong px-3 text-[13px] hover:border-ink" @click="pick(x)">
            {{ x.name }} <span class="text-muted">· {{ x.songs }}</span>
          </button>
        </div>
        <div v-if="manual.length" class="flex flex-col gap-1 rounded-2xl bg-surface p-3">
          <label v-for="x in manual" :key="x.id" class="flex items-center gap-3 py-1">
            <input v-model="manualKeep" type="radio" :value="x.id" name="merge-manual" class="size-4 accent-accent" />
            <span class="min-w-0 flex-1 truncate text-[15px]">{{ x.name }} <span class="text-[13px] text-muted">· {{ songs(x.songs) }}</span></span>
            <button type="button" class="grid size-8 place-items-center text-muted" :aria-label="t('common.remove')" @click.prevent="unpick(x.id)"><X :size="16" /></button>
          </label>
          <p class="text-[12px] text-muted">{{ t('merge.keepHelp') }}</p>
          <button type="button" class="mt-1 h-10 self-start rounded-full bg-ink px-5 text-[14px] text-on-ink disabled:opacity-50" :disabled="busy || manual.length < 2" @click="run(manualKeep!, manual.map((m) => m.id))">
            {{ t('merge.merge') }}
          </button>
        </div>
      </section>

      <!-- suggestions -->
      <section class="flex flex-col gap-2.5">
        <h3 class="font-medium">{{ t('merge.suggested') }}<span v-if="groups.length" class="text-muted"> {{ groups.length }}</span></h3>
        <p v-if="loaded && !groups.length" class="text-[14px] font-light text-muted">{{ t('merge.none') }}</p>
        <div v-for="(g, gi) in groups" :key="g.items[0].id" class="flex flex-col gap-1 rounded-2xl border border-line p-3">
          <div v-for="x in g.items" :key="x.id" class="flex items-center gap-3 py-1">
            <input v-model="g.keep" type="radio" :value="x.id" :name="`merge-keep-${gi}`" class="size-4 flex-none accent-accent" :aria-label="t('merge.keepThis', { name: x.name })" @change="g.picked.add(x.id)" />
            <span class="min-w-0 flex-1 truncate text-[15px]" :class="g.picked.has(x.id) ? '' : 'text-muted line-through'">{{ x.name }} <span class="text-[13px] text-muted no-underline">· {{ songs(x.songs) }}</span></span>
            <input v-if="x.id !== g.keep" type="checkbox" :checked="g.picked.has(x.id)" class="size-4 flex-none accent-accent" :aria-label="t('merge.include', { name: x.name })" @change="toggle(g, x.id)" />
            <span v-else class="flex-none text-[12px] text-accent">{{ t('merge.kept') }}</span>
          </div>
          <button type="button" class="mt-1 h-9 self-start rounded-full border border-ink px-4 text-[14px] disabled:opacity-50" :disabled="busy || g.picked.size < 2" @click="run(g.keep, [...g.picked])">
            {{ t('merge.mergeInto', { name: g.items.find((x) => x.id === g.keep)?.name }) }}
          </button>
        </div>
      </section>

      <!-- done so far -->
      <section v-if="merged.length" class="flex flex-col gap-1.5">
        <h3 class="font-medium">{{ t('merge.merged') }}</h3>
        <div v-for="m in merged" :key="m.name" class="flex items-center gap-3 py-1 text-[14px]">
          <span class="min-w-0 flex-1 truncate">{{ m.name }} <span class="text-muted">→ {{ m.target }}</span></span>
          <button type="button" class="h-8 flex-none rounded-full border border-line-strong px-3 text-[13px] disabled:opacity-50" :disabled="busy" @click="undo(m.name)">{{ t('merge.undo') }}</button>
        </div>
        <p class="text-[12px] font-light text-muted">{{ t('merge.undoHelp') }}</p>
      </section>
    </div>
  </BaseModal>
</template>
