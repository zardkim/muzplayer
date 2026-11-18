<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ChevronDown, ChevronUp, Minus, Plus, Search } from '@lucide/vue'
import { api } from '../api'
import { duration as clock } from '../format'
import { errorMessage } from '../i18n'
import { useLyrics } from '../stores/lyrics'
import { usePlayer } from '../stores/player'
import { useUi } from '../stores/ui'
import BaseModal from './BaseModal.vue'

// Admins fix a song's lyrics (backend api/lyrics_admin.py): wrong ones, or out of time. Lyrics to
// choose from come from AlSong (the file itself first), Bugs and LRCLIB; the one chosen (edited
// here if need be, its timing shifted: written into the lines) is saved as the song's .lrc in
// app/lrc and shown ahead of its own. Or none at all, or back to finding them by themselves. While the song plays, the line it is at shows
// under the shift, so the timing can be set by ear.
const { t } = useI18n()
const ui = useUi()
const player = usePlayer()
const lyricsStore = useLyrics()
const target = ui.lyricsAdmin!

interface Info {
  track: { id: number; title: string; artist: string; album: string; duration: number | null }
  own: string | null
  saved: { lrc: string | null; source: string | null; pinned: boolean } | null
  file: string | null // the .lrc under app/
  shown: 'pinned' | 'hidden' | 'own' | 'fetched' | 'none'
}
interface Candidate { source: 'alsong' | 'bugs' | 'lrclib'; title: string; artist: string; album: string; duration?: number | null; lrc: string; synced: boolean; lines: number; first: number | null; file?: boolean }

const info = ref<Info | null>(null)
const title = ref(target.title)
const artist = ref(target.artist)
const sources = ref<string[]>(['alsong', 'bugs', 'lrclib'])
const results = ref<Candidate[] | null>(null)
const failed = ref<string[]>([])
const open = ref(-1) // the candidate previewed
const text = ref('')
const source = ref<string>('manual')
const offset = ref(0) // seconds, + later
const busy = ref<'' | 'search' | 'save'>('')

onMounted(async () => {
  try {
    const r = await api<Info>(`/admin/lyrics/${target.trackId}`)
    info.value = r
    title.value = r.track.title
    artist.value = r.track.artist
    if (r.saved?.pinned) {
      text.value = r.saved.lrc ?? ''
      source.value = r.saved.source ?? 'manual'
    } else if (r.shown === 'own' && r.own) {
      text.value = r.own
      source.value = 'own'
    } else if (r.saved?.lrc) {
      text.value = r.saved.lrc
      source.value = r.saved.source ?? 'manual'
    }
  } catch (e) {
    ui.notify(errorMessage(e), true)
    ui.lyricsAdmin = null
  }
})

async function search() {
  busy.value = 'search'
  open.value = -1
  try {
    const r = await api<{ items: Candidate[]; failed: string[] }>(`/admin/lyrics/${target.trackId}/search`, {
      method: 'POST',
      body: { title: title.value.trim(), artist: artist.value.trim(), sources: sources.value },
    })
    results.value = r.items
    failed.value = r.failed
  } catch (e) {
    ui.notify(errorMessage(e), true)
  } finally {
    busy.value = ''
  }
}

function choose(c: Candidate) {
  text.value = c.lrc
  source.value = c.source
  offset.value = 0
}

// a light reading of the text for the preview (the server's lyrics.py is what counts)
const STAMP = /\[(\d{1,3}):(\d{1,2})(?:[.:,](\d{1,3}))?\]/g
function lines(lrc: string): [number, string][] {
  const out: [number, string][] = []
  for (const raw of lrc.split(/\r?\n/)) {
    const stamps = [...raw.matchAll(STAMP)]
    if (!stamps.length || stamps[0].index !== 0) continue
    const words = raw.replace(STAMP, '').trim()
    for (const m of stamps) out.push([Number(m[1]) * 60 + Number(m[2]) + (m[3] ? Number(`0.${m[3]}`) : 0), words])
  }
  return out.sort((a, b) => a[0] - b[0])
}
const preview = (c: Candidate) => lines(c.lrc).slice(0, 8)
const stamp = (s: number) => `${Math.floor(s / 60)}:${(s % 60).toFixed(1).padStart(4, '0')}`

// while this song plays: the line it is at, with the shift
const playing = computed(() => player.mode === 'music' && player.current?.id === target.trackId)
const parsed = computed(() => lines(text.value))
const nowLine = computed(() => {
  if (!playing.value) return null
  const at = player.currentTime - offset.value
  let line: [number, string] | null = null
  for (const l of parsed.value) if (l[0] <= at) line = l
  return line
})
function shift(by: number) {
  offset.value = Math.round((offset.value + by) * 10) / 10
}

async function save(lrc: string | null) {
  busy.value = 'save'
  try {
    const r = await api<{ file: string | null }>(`/admin/lyrics/${target.trackId}`, { method: 'PUT', body: { lrc, source: lrc ? source.value : 'manual', offset_ms: Math.round(offset.value * 1000) } })
    lyricsStore.reload(target.trackId)
    ui.notify(r.file ? t('lyricsAdmin.saved', { file: `app/${r.file}` }) : t('lyricsAdmin.hiddenDone'))
    ui.lyricsAdmin = null
  } catch (e) {
    ui.notify(errorMessage(e), true)
  } finally {
    busy.value = ''
  }
}
async function reset() {
  if (!confirm(t('lyricsAdmin.resetConfirm'))) return
  await api(`/admin/lyrics/${target.trackId}`, { method: 'DELETE' }).catch((e) => ui.notify(errorMessage(e), true))
  lyricsStore.reload(target.trackId)
  ui.notify(t('lyricsAdmin.resetDone'))
  ui.lyricsAdmin = null
}

const input = 'h-10 w-full min-w-0 rounded-xl border border-line-strong bg-bg px-3 text-[15px] outline-none focus:border-ink'
const SOURCE_NAMES: Record<string, string> = { alsong: 'lyricsAdmin.alsong', bugs: 'lyricsAdmin.bugs', lrclib: 'LRCLIB', manual: 'lyricsAdmin.manual', own: 'lyricsAdmin.own' }
const sourceName = (s: string | null | undefined) => (s && SOURCE_NAMES[s] ? (s === 'lrclib' ? 'LRCLIB' : t(SOURCE_NAMES[s])) : s ?? '')
</script>

<template>
  <BaseModal wide :title="t('lyricsAdmin.title', { title: target.title })" @close="ui.lyricsAdmin = null">
    <p class="-mt-2 mb-4 truncate text-[14px] font-light text-muted">{{ target.artist }}</p>
    <p v-if="!info" class="text-[15px] text-muted">{{ t('common.loading') }}</p>
    <div v-else class="flex flex-col gap-5">
      <!-- what plays now -->
      <p class="rounded-2xl bg-surface px-3.5 py-2.5 text-[14px]">
        {{ t(`lyricsAdmin.shown_${info.shown}`, { source: sourceName(info.saved?.source) }) }}
        <span v-if="info.file" class="mt-0.5 block break-all font-mono text-[12px] text-muted">app/{{ info.file }}</span>
      </p>

      <!-- look for others -->
      <section class="flex flex-col gap-2.5">
        <h3 class="text-[15px] font-medium">{{ t('lyricsAdmin.find') }}</h3>
        <div class="grid grid-cols-1 gap-2 sm:grid-cols-[1fr_1fr_auto]">
          <input v-model="title" type="text" :class="input" :placeholder="t('extractTags.title')" :aria-label="t('extractTags.title')" @keydown.enter="search" />
          <input v-model="artist" type="text" :class="input" :placeholder="t('extractTags.artist')" :aria-label="t('extractTags.artist')" @keydown.enter="search" />
          <button type="button" class="flex h-10 items-center justify-center gap-1.5 rounded-full bg-ink px-4 text-[14px] text-on-ink disabled:opacity-50" :disabled="!!busy || !title.trim() || !sources.length" @click="search">
            <Search :size="15" :stroke-width="1.8" />{{ busy === 'search' ? t('lyricsAdmin.searching') : t('lyricsAdmin.search') }}
          </button>
        </div>
        <div class="flex flex-wrap gap-x-4 gap-y-1 text-[14px]">
          <label v-for="s in ['alsong', 'bugs', 'lrclib']" :key="s" class="flex items-center gap-1.5">
            <input v-model="sources" type="checkbox" :value="s" class="size-4 accent-accent" />{{ sourceName(s) }}
          </label>
        </div>
        <p v-if="failed.length" class="text-[13px] text-danger">{{ t('lyricsAdmin.failed', { names: failed.map(sourceName).join(', ') }) }}</p>
        <p v-if="results && !results.length" class="text-[14px] font-light text-muted">{{ t('lyricsAdmin.noResults') }}</p>
        <ul v-if="results?.length" class="flex max-h-[40vh] flex-col overflow-y-auto rounded-2xl border border-line">
          <li v-for="(c, i) in results" :key="i" class="border-b border-line px-3 py-2.5 last:border-0">
            <div class="flex items-center gap-2">
              <span class="flex-none rounded-full bg-surface px-2 py-0.5 text-[11px] font-medium">{{ sourceName(c.source) }}</span>
              <span class="flex min-w-0 flex-1 flex-col">
                <span class="truncate text-[14px]">{{ c.title }}<span class="text-muted"> · {{ c.artist }}</span></span>
                <span class="truncate text-[12px] text-muted">
                  <template v-if="c.file">{{ t('lyricsAdmin.fileMatch') }} · </template>
                  {{ c.synced ? t('lyricsAdmin.syncedLines', { n: c.lines }) : t('lyricsAdmin.plain') }}
                  <template v-if="c.first != null"> · {{ t('lyricsAdmin.firstAt', { at: stamp(c.first) }) }}</template>
                  <template v-if="c.duration && info.track.duration"> · {{ clock(c.duration) }} ({{ t('lyricsAdmin.songLength', { at: clock(info.track.duration) }) }})</template>
                  <template v-if="c.album"> · {{ c.album }}</template>
                </span>
              </span>
              <button type="button" class="grid size-8 flex-none place-items-center rounded-full text-muted hover:bg-surface hover:text-ink" :aria-label="t('lyricsAdmin.preview')" :aria-expanded="open === i" @click="open = open === i ? -1 : i">
                <component :is="open === i ? ChevronUp : ChevronDown" :size="16" />
              </button>
              <button type="button" class="pill-sm flex-none" @click="choose(c)">{{ t('lyricsAdmin.use') }}</button>
            </div>
            <ol v-if="open === i" class="mt-2 flex flex-col gap-0.5 pl-1 text-[13px]">
              <li v-for="([at, words], k) in preview(c)" :key="k" class="flex gap-2"><span class="w-12 flex-none font-display text-muted">{{ stamp(at) }}</span>{{ words || '♪' }}</li>
              <li v-if="!c.synced" class="whitespace-pre-line text-muted">{{ c.lrc.slice(0, 300) }}</li>
            </ol>
          </li>
        </ul>
      </section>

      <!-- the lyrics kept -->
      <section class="flex flex-col gap-2.5">
        <h3 class="flex items-center justify-between text-[15px] font-medium">
          {{ t('lyricsAdmin.text') }}<span class="text-[12px] font-normal text-muted">{{ sourceName(source) }}</span>
        </h3>
        <textarea v-model="text" rows="8" spellcheck="false" class="w-full rounded-xl border border-line-strong bg-bg p-3 font-mono text-[13px] leading-relaxed outline-none focus:border-ink" :placeholder="t('lyricsAdmin.textHelp')" @input="source = 'manual'" />
        <div class="flex flex-wrap items-center gap-2 text-[14px]">
          <span>{{ t('lyricsAdmin.offset') }}</span>
          <button type="button" class="grid size-8 place-items-center rounded-full border border-line-strong hover:border-ink" :aria-label="t('lyricsAdmin.earlier')" @click="shift(-0.1)"><Minus :size="14" /></button>
          <input v-model.number="offset" type="number" step="0.1" min="-60" max="60" class="h-8 w-20 rounded-lg border border-line-strong bg-bg px-2 text-center text-[14px] tabular-nums" :aria-label="t('lyricsAdmin.offset')" />
          <button type="button" class="grid size-8 place-items-center rounded-full border border-line-strong hover:border-ink" :aria-label="t('lyricsAdmin.later')" @click="shift(0.1)"><Plus :size="14" /></button>
          <span class="text-[12px] text-muted">{{ t('lyricsAdmin.offsetHelp') }}</span>
        </div>
        <p v-if="playing" class="rounded-xl bg-surface px-3 py-2 text-[14px]">
          <span class="font-display text-[12px] text-muted">{{ stamp(player.currentTime) }}</span>
          <span class="ml-2">{{ nowLine ? nowLine[1] || '♪' : '…' }}</span>
        </p>
        <p v-else class="text-[12px] text-muted">{{ t('lyricsAdmin.playToCheck') }}</p>
      </section>

      <div class="flex flex-wrap items-center justify-between gap-2">
        <div class="flex gap-3">
          <button type="button" class="text-[13px] text-muted underline hover:text-ink disabled:opacity-50" :disabled="!!busy" @click="save(null)">{{ t('lyricsAdmin.hide') }}</button>
          <button v-if="info.saved" type="button" class="text-[13px] text-muted underline hover:text-ink disabled:opacity-50" :disabled="!!busy" @click="reset">{{ t('lyricsAdmin.reset') }}</button>
        </div>
        <button type="button" class="h-11 rounded-full bg-ink px-6 text-[15px] text-on-ink disabled:opacity-50" :disabled="!!busy || !text.trim()" @click="save(text)">
          {{ busy === 'save' ? t('extractTags.saving') : t('common.save') }}
        </button>
      </div>
    </div>
  </BaseModal>
</template>
