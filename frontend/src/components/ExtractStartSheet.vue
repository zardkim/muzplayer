<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api'
import { errorMessage } from '../i18n'
import { useUi } from '../stores/ui'
import type { VideoListItem } from '../types'
import BaseModal from './BaseModal.vue'
import CoverArt from './CoverArt.vue'

// Taking a music video's sound out as a song (backend extract.py): m4a (AAC kept as it is) or mp3.
// Into an album of its own, or into one the same singer's songs were already taken out into (its
// next number; its art kept, or made anew from its songs' pictures; its name kept or changed).
// The job runs in the background; the jobs sheet shows it.
const props = defineProps<{ video: VideoListItem }>()
const emit = defineEmits<{ close: []; queued: [] }>()
const { t } = useI18n()
const ui = useUi()
interface Status { folder_ok: boolean; ytdlp: string | null; youtube: boolean; format: 'm4a' | 'mp3' }
const status = ref<Status | null>(null)
const format = ref<'m4a' | 'mp3'>('m4a')
const busy = ref(false)
interface Choice { id: number; title: string; artist: string; track_count: number; has_cover: boolean; cover_v: number }
const albums = ref<Choice[]>([])
const into = ref<Choice | null>(null) // null: an album of its own
const art = ref<'keep' | 'new'>('keep')
const albumName = ref('')
function choose(a: Choice | null) {
  into.value = a
  albumName.value = a?.title ?? ''
}
onMounted(async () => {
  const [s, a] = await Promise.all([
    api<Status>('/extract/status').catch(() => null),
    api<{ items: Choice[] }>(`/videos/${props.video.id}/extract/albums`).catch(() => ({ items: [] })),
  ])
  status.value = s
  albums.value = a.items
  if (s) format.value = s.format
})
const blocked = () => {
  const s = status.value
  if (!s) return ''
  if (!s.folder_ok) return t('extract.noFolder')
  if (props.video.youtube_id && !s.youtube) return t('extract.youtubeOff')
  if (props.video.youtube_id && !s.ytdlp) return t('extract.noYtdlp')
  return ''
}
async function start() {
  busy.value = true
  try {
    const name = albumName.value.trim()
    const album = into.value ? { album_id: into.value.id, cover: art.value, title: name && name !== into.value.title ? name : null } : null
    await api(`/videos/${props.video.id}/extract`, { method: 'POST', body: { format: format.value, album } })
    ui.notify(t('extract.queued'))
    emit('queued')
  } catch (e) {
    ui.notify(errorMessage(e), true)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <BaseModal :title="t('extract.title')" @close="emit('close')">
    <div class="flex flex-col gap-4">
      <p class="text-[15px] font-medium">{{ video.title }}</p>
      <p class="text-[13px] leading-relaxed text-muted">{{ t('extract.help') }}</p>
      <div class="flex flex-col gap-2" role="radiogroup" :aria-label="t('extract.format')">
        <label v-for="f in (['m4a', 'mp3'] as const)" :key="f" class="flex items-start gap-3 rounded-xl border px-3.5 py-3" :class="format === f ? 'border-ink' : 'border-line'">
          <input v-model="format" type="radio" :value="f" class="mt-1 accent-accent" />
          <span class="flex flex-col"><span class="text-[15px] font-medium uppercase">{{ f }}</span><span class="text-[13px] text-muted">{{ t(`extract.format_${f}`) }}</span></span>
        </label>
      </div>
      <!-- the same singer's albums taken out before: this song as their next one -->
      <div v-if="albums.length" class="flex flex-col gap-2" role="radiogroup" :aria-label="t('extract.album')">
        <p class="text-[14px] font-medium">{{ t('extract.album') }}</p>
        <label class="flex items-center gap-3 rounded-xl border px-3.5 py-3" :class="!into ? 'border-ink' : 'border-line'">
          <input type="radio" :checked="!into" class="accent-accent" @change="choose(null)" />
          <span class="flex flex-col"><span class="text-[15px]">{{ t('extract.albumNew') }}</span><span class="text-[13px] text-muted">{{ t('extract.albumNewHelp') }}</span></span>
        </label>
        <label v-for="a in albums" :key="a.id" class="flex items-center gap-3 rounded-xl border px-3.5 py-2.5" :class="into?.id === a.id ? 'border-ink' : 'border-line'">
          <input type="radio" :checked="into?.id === a.id" class="accent-accent" @change="choose(a)" />
          <CoverArt :album-id="a.id" :has-cover="a.has_cover" :version="a.cover_v" rounded="rounded-md" class="size-10 flex-none" />
          <span class="flex min-w-0 flex-col">
            <span class="truncate text-[15px]">{{ a.title }}</span>
            <span class="truncate text-[13px] text-muted">{{ a.artist }} · {{ t('common.tracks', a.track_count) }} · {{ t('extract.albumNext', { n: a.track_count + 1 }) }}</span>
          </span>
        </label>
        <template v-if="into">
          <label class="mt-1 flex flex-col gap-1 text-[13px] text-muted">
            {{ t('extract.albumName') }}
            <input v-model="albumName" type="text" maxlength="300" class="h-11 rounded-xl border border-line-strong bg-bg px-3.5 text-[15px] text-ink" />
          </label>
          <div class="flex flex-col gap-1.5" role="radiogroup" :aria-label="t('extract.albumArt')">
            <p class="text-[13px] text-muted">{{ t('extract.albumArt') }}</p>
            <label v-for="c in (['keep', 'new'] as const)" :key="c" class="flex items-start gap-2.5 text-[14px]">
              <input v-model="art" type="radio" :value="c" class="mt-1 accent-accent" />
              <span>{{ t(`extract.albumArt_${c}`) }}<span class="block text-[12px] text-muted">{{ t(`extract.albumArtHelp_${c}`) }}</span></span>
            </label>
          </div>
        </template>
      </div>
      <p v-if="blocked()" class="text-[13px] leading-relaxed text-danger">{{ blocked() }}</p>
      <button type="button" class="h-12 rounded-full bg-ink text-on-ink disabled:opacity-50" :disabled="busy || !status || !!blocked()" @click="start">{{ t('extract.start') }}</button>
    </div>
  </BaseModal>
</template>
