<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { Plus, X } from '@lucide/vue'
import { api } from '../api'
import { errorMessage } from '../i18n'
import type { Genre, Playlist, RuleField, SmartRule, SmartRules } from '../types'
import BaseModal from './BaseModal.vue'

// Make or change a smart playlist: rules on the user's plays, stars and likes and the songs' tags.
const props = defineProps<{ playlist?: Playlist }>()
const emit = defineEmits<{ close: []; saved: [playlist: Playlist] }>()
const { t } = useI18n()

const OPS: Record<RuleField, string[]> = {
  genre: ['is', 'is_not'],
  artist: ['contains', 'not_contains'],
  year: ['between'],
  rating: ['gte', 'lte', 'none'],
  favorite: ['is'],
  plays: ['gte', 'lte'],
  last_played: ['within_days', 'not_within_days'],
  added: ['within_days'],
  folder: ['is', 'is_not'],
  duration: ['gte', 'lte'],
}
const FIELDS = Object.keys(OPS) as RuleField[]
const FOLDERS = ['album', 'compilation', 'chart', 'theme']
const SORTS: SmartRules['sort'][] = ['random', 'plays', 'recent', 'title', 'rating', 'last_played']

function fresh(field: RuleField): SmartRule {
  const value = {
    genre: '', artist: '', year: [2010, 2019], rating: 4, favorite: true, plays: 5,
    last_played: 30, added: 30, folder: 'album', duration: 300,
  }[field]
  return { field, op: OPS[field][0], value }
}

const name = ref(props.playlist?.name ?? '')
const rules = ref<SmartRules>(
  props.playlist?.rules ? JSON.parse(JSON.stringify(props.playlist.rules)) : { match: 'all', rules: [fresh('rating')], sort: 'random', limit: 100 },
)
const genres = ref<string[]>([])
const busy = ref(false)
const error = ref('')

onMounted(async () => {
  genres.value = (await api<{ items: Genre[] }>('/genres').catch(() => ({ items: [] }))).items.map((g) => g.name)
})

function setField(i: number, field: RuleField) {
  rules.value.rules[i] = fresh(field)
}

const field = 'h-10 rounded-full bg-surface px-3 text-[15px] outline-none focus:ring-2 focus:ring-ink'

async function save() {
  busy.value = true
  error.value = ''
  try {
    const body = { name: name.value.trim(), rules: rules.value }
    const p = props.playlist
      ? await api<Playlist>(`/playlists/${props.playlist.id}`, { method: 'PATCH', body })
      : await api<Playlist>('/playlists', { method: 'POST', body })
    emit('saved', p)
  } catch (e) {
    error.value = errorMessage(e)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <BaseModal :title="playlist ? t('smart.edit') : t('smart.new')" @close="emit('close')">
    <form class="flex flex-col gap-4" @submit.prevent="save">
      <p class="text-[14px] font-light text-muted">{{ t('smart.intro') }}</p>
      <label class="flex flex-col gap-1.5 text-[13px] text-muted">
        {{ t('playlists.name') }}
        <input v-model="name" required maxlength="200" class="h-12 rounded-full bg-surface px-4 text-base text-ink outline-none focus:ring-2 focus:ring-ink" />
      </label>

      <label class="flex items-center gap-2 text-[14px]">
        {{ t('smart.match') }}
        <select v-model="rules.match" :class="field">
          <option value="all">{{ t('smart.matchAll') }}</option>
          <option value="any">{{ t('smart.matchAny') }}</option>
        </select>
      </label>

      <p v-if="!rules.rules.length" class="text-[14px] font-light text-muted">{{ t('smart.noRules') }}</p>
      <div v-for="(r, i) in rules.rules" :key="i" class="flex flex-wrap items-center gap-2 rounded-2xl border border-line p-2.5">
        <select :value="r.field" :class="field" :aria-label="t('smart.match')" @change="setField(i, ($event.target as HTMLSelectElement).value as RuleField)">
          <option v-for="f in FIELDS" :key="f" :value="f">{{ t(`smart.fields.${f}`) }}</option>
        </select>
        <select v-if="OPS[r.field].length > 1" v-model="r.op" :class="field">
          <option v-for="o in OPS[r.field]" :key="o" :value="o">{{ t(`smart.ops.${o}`) }}</option>
        </select>

        <template v-if="r.field === 'genre'">
          <input v-model="r.value" list="smart-genres" required maxlength="200" :class="[field, 'min-w-0 flex-1']" />
        </template>
        <input v-else-if="r.field === 'artist'" v-model="r.value" required maxlength="200" :class="[field, 'min-w-0 flex-1']" />
        <template v-else-if="r.field === 'year'">
          <input v-model.number="(r.value as number[])[0]" type="number" min="1900" max="2100" :class="[field, 'w-24']" />
          <span>–</span>
          <input v-model.number="(r.value as number[])[1]" type="number" min="1900" max="2100" :class="[field, 'w-24']" />
        </template>
        <select v-else-if="r.field === 'rating' && r.op !== 'none'" v-model.number="r.value" :class="field">
          <option v-for="n in 5" :key="n" :value="n">★ {{ n }}</option>
        </select>
        <select v-else-if="r.field === 'favorite'" v-model="r.value" :class="field">
          <option :value="true">{{ t('smart.yes') }}</option>
          <option :value="false">{{ t('smart.no') }}</option>
        </select>
        <select v-else-if="r.field === 'folder'" v-model="r.value" :class="field">
          <option v-for="f in FOLDERS" :key="f" :value="f">{{ t(`smart.folders.${f}`) }}</option>
        </select>
        <template v-else-if="r.field === 'duration'">
          <!-- minutes on screen, seconds in the rule -->
          <input :value="Math.round(Number(r.value) / 60)" type="number" min="0" max="600" :class="[field, 'w-20']" @input="r.value = Number(($event.target as HTMLInputElement).value) * 60" />
          <span class="text-[14px]">{{ t('smart.minutes') }}</span>
        </template>
        <template v-else-if="r.field !== 'rating'">
          <input v-model.number="r.value" type="number" min="0" max="100000" :class="[field, 'w-24']" />
          <span v-if="r.field === 'last_played' || r.field === 'added'" class="text-[14px]">{{ t('smart.days') }}</span>
        </template>

        <button type="button" class="ml-auto grid size-10 place-items-center text-muted" :aria-label="t('smart.removeRule')" @click="rules.rules.splice(i, 1)">
          <X :size="18" />
        </button>
      </div>
      <datalist id="smart-genres"><option v-for="g in genres" :key="g" :value="g" /></datalist>
      <button v-if="rules.rules.length < 20" type="button" class="flex h-10 items-center gap-1 self-start rounded-full border border-line-strong px-3.5 text-[14px]" @click="rules.rules.push(fresh('genre'))">
        <Plus :size="16" />{{ t('smart.addRule') }}
      </button>

      <div class="flex flex-wrap gap-3">
        <label class="flex items-center gap-2 text-[14px]">
          {{ t('smart.sort') }}
          <select v-model="rules.sort" :class="field">
            <option v-for="s in SORTS" :key="s" :value="s">{{ t(`smart.sorts.${s}`) }}</option>
          </select>
        </label>
        <label class="flex items-center gap-2 text-[14px]">
          {{ t('smart.limit') }}
          <input v-model.number="rules.limit" type="number" min="1" max="500" :class="[field, 'w-24']" />
        </label>
      </div>

      <p v-if="error" class="text-[14px] text-danger" role="alert">{{ error }}</p>
      <button type="submit" class="h-12 rounded-full bg-ink text-white disabled:opacity-40" :disabled="busy || !name.trim()">{{ t('common.save') }}</button>
    </form>
  </BaseModal>
</template>
