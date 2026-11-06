<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Clock, Disc3, Music2, Search, User, X } from '@lucide/vue'
import { api, query } from '../api'
import { useSearchHistory } from '../searchHistory'

// The music search box (top bar on a PC, the search page on a phone). Empty and focused: the recent
// searches; while typing: recent ones that fit, then words from the library (artists, albums, songs;
// Korean initials too). Arrows move, Enter searches the one picked (or what was typed). `only`: a
// library tab's box (albums, artists, songs) suggests that kind alone.
const props = withDefaults(defineProps<{ id: string; placeholder: string; suggest?: boolean; large?: boolean; only?: 'artist' | 'album' | 'track' }>(), { suggest: true })
const text = defineModel<string>({ required: true })
const emit = defineEmits<{ submit: [q: string] }>()
const { t } = useI18n()
const history = useSearchHistory()

type Item = { text: string; kind: 'recent' | 'artist' | 'album' | 'track'; sub?: string }
const open = ref(false)
const active = ref(-1)
const library = ref<Item[]>([])
let timer: number | undefined
let asked = 0

const items = computed<Item[]>(() => {
  if (!props.suggest) return []
  const q = text.value.trim().toLocaleLowerCase()
  const recent = history.recent.value.filter((r) => !q || r.toLocaleLowerCase().includes(q)).slice(0, q ? 3 : 10)
  const seen = new Set(recent.map((r) => r.toLocaleLowerCase()))
  return [
    ...recent.map((r) => ({ text: r, kind: 'recent' as const })),
    ...(q ? library.value.filter((s) => !seen.has(s.text.toLocaleLowerCase())) : []),
  ]
})

watch(text, (q) => {
  active.value = -1
  clearTimeout(timer)
  if (!props.suggest || !q.trim()) {
    library.value = []
    return
  }
  timer = window.setTimeout(async () => {
    const mine = ++asked
    try {
      const r = await api<{ items: Item[] }>(`/search/suggest${query({ q: q.trim(), limit: 8 })}`)
      if (mine === asked) library.value = props.only ? r.items.filter((x) => x.kind === props.only) : r.items
    } catch {
      /* no suggestions: the search still works */
    }
  }, 180)
})
onUnmounted(() => clearTimeout(timer))

function go(q: string) {
  const s = q.trim()
  if (!s) return
  text.value = s
  open.value = false
  ;(document.getElementById(props.id) as HTMLInputElement | null)?.blur()
  emit('submit', s)
}
function key(e: KeyboardEvent) {
  if (!open.value || !items.value.length) return
  if (e.key === 'ArrowDown') active.value = (active.value + 1) % items.value.length
  else if (e.key === 'ArrowUp') active.value = active.value <= 0 ? items.value.length - 1 : active.value - 1
  else if (e.key === 'Escape') open.value = false
  else return
  e.preventDefault()
}
function submit() {
  go(active.value >= 0 && items.value[active.value] ? items.value[active.value].text : text.value)
}
// a tap on a suggestion lands before the box loses focus
function blur() {
  window.setTimeout(() => (open.value = false), 150)
}
const icons = { recent: Clock, artist: User, album: Disc3, track: Music2 }
</script>

<template>
  <form role="search" class="relative flex items-center gap-2.5 rounded-full bg-surface" :class="large ? 'h-[50px] px-[18px]' : 'h-[46px] px-[18px]'" @submit.prevent="submit">
    <Search :size="large ? 22 : 20" :stroke-width="1.4" class="flex-none text-muted" aria-hidden="true" />
    <label :for="id" class="sr-only">{{ t('search.label') }}</label>
    <input
      :id="id"
      v-model="text"
      type="search"
      enterkeyhint="search"
      autocomplete="off"
      role="combobox"
      :aria-expanded="open && items.length > 0"
      :aria-controls="`${id}-list`"
      :aria-activedescendant="active >= 0 ? `${id}-opt-${active}` : undefined"
      :placeholder="placeholder"
      class="min-w-0 flex-1 bg-transparent font-light outline-none placeholder:text-muted"
      :class="large ? 'text-[17px]' : 'text-[15px]'"
      @focus="open = true"
      @input="open = true"
      @blur="blur"
      @keydown="key"
    />
    <div
      v-if="open && items.length"
      :id="`${id}-list`"
      role="listbox"
      class="absolute inset-x-0 top-full z-40 mt-2 flex max-h-[60vh] flex-col overflow-y-auto rounded-2xl border border-line bg-bg py-1.5 shadow-xl"
    >
      <div v-if="!text.trim()" class="flex items-center justify-between px-4 pb-1 pt-1.5 text-[12px] text-muted">
        <span>{{ t('search.recent') }}</span>
        <button type="button" class="hover:text-ink" @mousedown.prevent @click="history.clear()">{{ t('search.clearRecent') }}</button>
      </div>
      <div
        v-for="(it, i) in items"
        :id="`${id}-opt-${i}`"
        :key="`${it.kind}-${it.text}`"
        role="option"
        :aria-selected="i === active"
        class="flex cursor-pointer items-center gap-3 px-4 py-2.5 text-[15px]"
        :class="i === active ? 'bg-surface' : 'hover:bg-surface'"
        @mousedown.prevent
        @click="go(it.text)"
      >
        <component :is="icons[it.kind]" :size="16" :stroke-width="1.5" class="flex-none text-muted" />
        <span class="flex min-w-0 flex-1 items-baseline gap-2">
          <span class="truncate">{{ it.text }}</span>
          <span v-if="it.sub" class="truncate text-[12px] text-muted">{{ it.sub }}</span>
        </span>
        <button
          v-if="it.kind === 'recent'"
          type="button"
          class="-mr-2 grid size-8 flex-none place-items-center rounded-full text-muted hover:text-ink"
          :aria-label="`${t('search.removeRecent')}: ${it.text}`"
          @mousedown.prevent
          @click.stop="history.remove(it.text)"
        >
          <X :size="15" :stroke-width="1.6" />
        </button>
      </div>
    </div>
  </form>
</template>
