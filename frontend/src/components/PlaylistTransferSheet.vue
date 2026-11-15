<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ListMusic, ListVideo, Plus } from '@lucide/vue'
import { api } from '../api'
import { errorMessage } from '../i18n'
import { useLibrary } from '../stores/library'
import { useUi } from '../stores/ui'
import BaseModal from './BaseModal.vue'

// Songs (or videos) of one of my playlists copied or moved into another of the same kind: music
// to music, music videos to music videos (smart playlists neither give nor take: their songs come
// from their rules). The entries to take are ticked here (all, or those picked in the list
// before); a new playlist can be made on the way. Backend: POST …/transfer (me.py, videos.py).
const props = defineProps<{
  kind: 'music' | 'video'
  sourceId: number
  items: { entry: number; title: string; sub: string }[]
  picked?: number[] // entry ids ticked to begin with (else all)
}>()
const emit = defineEmits<{ close: []; done: [] }>()
const { t } = useI18n()
const library = useLibrary()
const ui = useUi()

const ticked = ref(new Set<number>(props.picked?.length ? props.picked : props.items.map((x) => x.entry)))
const allTicked = computed(() => ticked.value.size === props.items.length)
function tick(entry: number) {
  const s = new Set(ticked.value)
  if (s.has(entry)) s.delete(entry)
  else s.add(entry)
  ticked.value = s
}
const targets = computed(() =>
  props.kind === 'music'
    ? library.editablePlaylists.filter((p) => p.id !== props.sourceId).map((p) => ({ id: p.id, name: p.name, count: p.track_count ?? 0 }))
    : library.videoPlaylists.filter((p) => p.id !== props.sourceId).map((p) => ({ id: p.id, name: p.name, count: p.count })),
)
const target = ref<number | 'new' | null>(null)
const newName = ref('')
const busy = ref(false)

async function go(mode: 'copy' | 'move') {
  if (!ticked.value.size || target.value === null) return
  busy.value = true
  try {
    let id = target.value
    if (id === 'new') {
      const name = newName.value.trim()
      if (!name) return
      id = props.kind === 'music'
        ? (await library.createPlaylist(name)).id
        : (await api<{ id: number }>('/video-playlists', { method: 'POST', body: { name } })).id
    }
    const base = props.kind === 'music' ? '/playlists' : '/video-playlists'
    const r = await api<{ added: number; skipped: number; removed: number }>(`${base}/${props.sourceId}/transfer`, {
      method: 'POST',
      body: { target_id: id, mode, entry_ids: allTicked.value ? null : [...ticked.value] },
    })
    ui.notify(t(mode === 'move' ? 'transfer.moved' : 'transfer.copied', { n: r.added }) + (r.skipped ? ` ${t('transfer.skipped', { n: r.skipped })}` : ''))
    await (props.kind === 'music' ? library.loadPlaylists() : library.loadVideoPlaylists()).catch(() => {})
    emit('done')
    emit('close')
  } catch (e) {
    ui.notify(errorMessage(e), true)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <BaseModal wide :title="t('transfer.title')" @close="emit('close')">
    <div class="flex flex-col gap-5">
      <!-- what to take -->
      <section class="flex flex-col gap-2">
        <div class="flex items-center justify-between">
          <h3 class="text-[15px] font-medium">{{ t(kind === 'music' ? 'transfer.songs' : 'transfer.videos', { n: ticked.size }) }}</h3>
          <button type="button" class="text-[13px] text-muted underline hover:text-ink" @click="ticked = allTicked ? new Set() : new Set(items.map((x) => x.entry))">
            {{ allTicked ? t('common.clearSelection') : t('common.selectAll') }}
          </button>
        </div>
        <ul class="flex max-h-[30vh] flex-col overflow-y-auto rounded-2xl border border-line">
          <li v-for="x in items" :key="x.entry" class="border-b border-line last:border-0">
            <label class="flex cursor-pointer items-center gap-3 px-3 py-2">
              <input type="checkbox" class="size-4 flex-none accent-ink" :checked="ticked.has(x.entry)" @change="tick(x.entry)" />
              <span class="flex min-w-0 flex-col">
                <span class="truncate text-[14px]">{{ x.title }}</span>
                <span v-if="x.sub" class="truncate text-[12px] text-muted">{{ x.sub }}</span>
              </span>
            </label>
          </li>
        </ul>
      </section>

      <!-- where to -->
      <section class="flex flex-col gap-2">
        <h3 class="text-[15px] font-medium">{{ t('transfer.to') }}</h3>
        <div class="flex max-h-[30vh] flex-col overflow-y-auto rounded-2xl border border-line">
          <label v-for="p in targets" :key="p.id" class="flex cursor-pointer items-center gap-3 border-b border-line px-3 py-2.5 last:border-0" :class="target === p.id ? 'bg-surface' : ''">
            <input v-model="target" type="radio" name="transfer-target" :value="p.id" class="size-4 accent-ink" />
            <component :is="kind === 'music' ? ListMusic : ListVideo" :size="18" :stroke-width="1.4" class="flex-none text-muted" />
            <span class="min-w-0 flex-1 truncate text-[15px]">{{ p.name }}</span>
            <span class="text-[12px] tabular-nums text-muted">{{ p.count }}</span>
          </label>
          <label class="flex cursor-pointer items-center gap-3 px-3 py-2.5" :class="target === 'new' ? 'bg-surface' : ''">
            <input v-model="target" type="radio" name="transfer-target" value="new" class="size-4 accent-ink" />
            <Plus :size="18" :stroke-width="1.6" class="flex-none text-muted" />
            <input v-model="newName" type="text" maxlength="200" :placeholder="t('transfer.newList')" class="h-9 min-w-0 flex-1 rounded-lg bg-transparent text-[15px] outline-none" @focus="target = 'new'" />
          </label>
        </div>
      </section>

      <div class="flex justify-end gap-2">
        <button type="button" class="h-11 rounded-full border border-line-strong px-5 text-[15px] hover:border-ink disabled:opacity-40" :disabled="busy || !ticked.size || target === null || (target === 'new' && !newName.trim())" @click="go('copy')">{{ t('transfer.copy') }}</button>
        <button type="button" class="h-11 rounded-full bg-ink px-5 text-[15px] text-on-ink disabled:opacity-40" :disabled="busy || !ticked.size || target === null || (target === 'new' && !newName.trim())" @click="go('move')">{{ t('transfer.move') }}</button>
      </div>
    </div>
  </BaseModal>
</template>
