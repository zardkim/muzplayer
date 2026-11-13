<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { CircleAlert, ImageUp, Search } from '@lucide/vue'
import { api } from '../api'
import { errorMessage } from '../i18n'
import { useUi } from '../stores/ui'
import BaseModal from './BaseModal.vue'
import CoverArt from './CoverArt.vue'

// Admin: an extracted song's tags (backend extract.py), written into its file — which is renamed to
// match (cover music/<artist>/<disc>-<track> <title>) and scanned in again, keeping its likes and
// playlist places. "Find again" fills the form from the song's video (the AI or its title, Bugs);
// nothing is saved until Save. The cover: as it is, the video's thumbnail, Bugs' album cover or a picture.
const props = defineProps<{ tracks: { id: number; title: string }[]; start?: number }>()
const emit = defineEmits<{ close: []; saved: [r: { track_id: number | null; album_id: number | null }] }>()
const { t } = useI18n()
const ui = useUi()

interface Tags { title: string; artist: string; album: string; album_artist: string; year: string; genre: string; track: number; disc: number }
interface Info { track_id: number; album_id: number | null; file_path: string; format: string; tags: Tags & { lyrics: boolean; cover: boolean }; video: { id: number; title: string; youtube_id: string | null } | null }
interface Suggestion { tags: Tags; review: string[]; original: { artist: string; title: string } | null; bugs_cover: string | null }

const trackId = ref(props.start ?? props.tracks[0]?.id)
const info = ref<Info | null>(null)
const form = ref<Tags>({ title: '', artist: '', album: '', album_artist: '', year: '', genre: '', track: 1, disc: 1 })
const found = ref<Suggestion | null>(null)
const cover = ref<'' | 'thumbnail' | 'bugs' | 'upload'>('')
const upload = ref('')
const lyrics = ref(false)
const busy = ref<'' | 'load' | 'find' | 'save'>('')

async function load() {
  busy.value = 'load'
  found.value = null
  cover.value = ''
  upload.value = ''
  lyrics.value = false
  try {
    info.value = await api<Info>(`/extract/tracks/${trackId.value}`)
    const { lyrics: _l, cover: _c, ...tags } = info.value.tags
    form.value = tags
  } catch (e) {
    ui.notify(errorMessage(e), true)
    emit('close')
  } finally {
    busy.value = ''
  }
}
onMounted(load)
watch(trackId, load)

async function findAgain() {
  busy.value = 'find'
  try {
    found.value = await api<Suggestion>(`/extract/tracks/${trackId.value}/suggest`, { method: 'POST' })
    form.value = { ...found.value.tags }
    if (found.value.bugs_cover && !cover.value) cover.value = 'bugs'
    if (!info.value?.tags.lyrics) lyrics.value = true
  } catch (e) {
    ui.notify(errorMessage(e), true)
  } finally {
    busy.value = ''
  }
}

function pick(file: File | undefined) {
  if (!file) return
  if (file.size > 8_000_000) return ui.notify(t('extractTags.tooLarge'), true)
  const reader = new FileReader()
  reader.onload = () => {
    upload.value = String(reader.result)
    cover.value = 'upload'
  }
  reader.readAsDataURL(file)
}

const review = computed(() => (found.value?.review ?? []).map((r) => t(`extract.review_${r}`)).join(' · '))

async function save() {
  busy.value = 'save'
  try {
    const r = await api<{ track_id: number | null; album_id: number | null }>(`/extract/tracks/${trackId.value}`, {
      method: 'PUT',
      body: {
        ...form.value,
        cover: cover.value || null,
        cover_url: cover.value === 'bugs' ? found.value?.bugs_cover : null,
        cover_data: cover.value === 'upload' ? upload.value : null,
        lyrics: lyrics.value,
      },
    })
    ui.notify(t('extractTags.saved'))
    emit('saved', r)
    emit('close')
  } catch (e) {
    ui.notify(errorMessage(e), true)
  } finally {
    busy.value = ''
  }
}

const FIELDS = [
  ['title', 'extractTags.title'], ['artist', 'extractTags.artist'], ['album', 'extractTags.album'], ['album_artist', 'extractTags.albumArtist'],
  ['year', 'extractTags.year'], ['genre', 'extractTags.genre'],
] as const
const input = 'h-10 w-full min-w-0 rounded-xl border border-line-strong bg-bg px-3 text-[15px] outline-none focus:border-ink'
</script>

<template>
  <BaseModal wide :title="t('extractTags.title_')" @close="emit('close')">
    <div class="flex flex-col gap-4">
      <select v-if="tracks.length > 1" v-model="trackId" :class="input">
        <option v-for="x in tracks" :key="x.id" :value="x.id">{{ x.title }}</option>
      </select>
      <p v-if="busy === 'load'" class="text-[14px] font-light text-muted">{{ t('common.loading') }}</p>
      <template v-else-if="info">
        <div class="flex flex-wrap items-center gap-2">
          <span class="min-w-0 flex-1 truncate text-[12px] text-muted" :title="info.file_path">{{ info.file_path }}</span>
          <button v-if="info.video" type="button" class="flex h-9 items-center gap-1.5 rounded-full border border-line-strong px-3.5 text-[14px] hover:border-ink disabled:opacity-50" :disabled="!!busy" @click="findAgain">
            <Search :size="15" :stroke-width="1.7" />{{ busy === 'find' ? t('extractTags.finding') : t('extractTags.findAgain') }}
          </button>
        </div>
        <p v-if="found && (review || found.original)" class="flex items-start gap-1.5 text-[13px]" :class="review ? 'text-danger' : 'text-muted'">
          <CircleAlert v-if="review" :size="14" :stroke-width="1.8" class="mt-0.5 flex-none" />
          <span>{{ [found.original ? t('extract.coverOf', { artist: found.original.artist }) : '', review ? `${t('extract.review')}: ${review}` : ''].filter(Boolean).join(' · ') }}</span>
        </p>

        <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <label v-for="[key, label] in FIELDS" :key="key" class="flex flex-col gap-1 text-[13px] text-muted">
            {{ t(label) }}
            <input v-model="form[key]" type="text" :class="input" class="text-ink" :required="key === 'title'" />
          </label>
          <div class="grid grid-cols-2 gap-3">
            <label class="flex flex-col gap-1 text-[13px] text-muted">{{ t('extractTags.track') }}<input v-model.number="form.track" type="number" min="1" max="999" :class="input" class="text-ink" /></label>
            <label class="flex flex-col gap-1 text-[13px] text-muted">{{ t('extractTags.disc') }}<input v-model.number="form.disc" type="number" min="1" max="99" :class="input" class="text-ink" /></label>
          </div>
        </div>

        <!-- the cover -->
        <section class="flex flex-col gap-2.5">
          <h3 class="text-[15px] font-medium">{{ t('extractTags.cover') }}</h3>
          <div class="flex flex-wrap gap-3">
            <button type="button" class="flex w-24 flex-col items-center gap-1 text-[12px]" :class="cover === '' ? 'font-medium' : 'text-muted'" @click="cover = ''">
              <span class="block size-24 overflow-hidden rounded-xl" :class="cover === '' ? 'ring-2 ring-ink' : 'ring-1 ring-line'">
                <CoverArt v-if="info.album_id" :album-id="info.album_id" :has-cover="info.tags.cover" rounded="rounded-none" />
              </span>{{ t('extractTags.coverKeep') }}
            </button>
            <button v-if="info.video" type="button" class="flex w-24 flex-col items-center gap-1 text-[12px]" :class="cover === 'thumbnail' ? 'font-medium' : 'text-muted'" @click="cover = 'thumbnail'">
              <span class="grid size-24 place-items-center overflow-hidden rounded-xl bg-surface" :class="cover === 'thumbnail' ? 'ring-2 ring-ink' : 'ring-1 ring-line'">
                <img v-if="info.video.youtube_id" :src="`https://i.ytimg.com/vi/${info.video.youtube_id}/hqdefault.jpg`" alt="" class="size-full object-cover" />
                <img v-else :src="`/api/v1/videos/${info.video.id}/thumb`" alt="" class="size-full object-cover" />
              </span>{{ t('extractTags.coverThumb') }}
            </button>
            <button v-if="found?.bugs_cover" type="button" class="flex w-24 flex-col items-center gap-1 text-[12px]" :class="cover === 'bugs' ? 'font-medium' : 'text-muted'" @click="cover = 'bugs'">
              <span class="block size-24 overflow-hidden rounded-xl" :class="cover === 'bugs' ? 'ring-2 ring-ink' : 'ring-1 ring-line'"><img :src="found.bugs_cover" alt="" class="size-full object-cover" /></span>{{ t('extractTags.coverBugs') }}
            </button>
            <label class="flex w-24 cursor-pointer flex-col items-center gap-1 text-[12px]" :class="cover === 'upload' ? 'font-medium' : 'text-muted'">
              <span class="grid size-24 place-items-center overflow-hidden rounded-xl bg-surface" :class="cover === 'upload' ? 'ring-2 ring-ink' : 'ring-1 ring-line'">
                <img v-if="upload" :src="upload" alt="" class="size-full object-cover" />
                <ImageUp v-else :size="24" :stroke-width="1.4" />
              </span>{{ t('extractTags.coverUpload') }}
              <input type="file" accept="image/jpeg,image/png,image/webp" class="sr-only" @change="pick(($event.target as HTMLInputElement).files?.[0])" />
            </label>
          </div>
        </section>

        <label class="flex items-start gap-2.5 text-[14px]">
          <input v-model="lyrics" type="checkbox" class="mt-0.5 size-4 accent-accent" />
          <span>{{ t('extractTags.lyrics') }}<span class="block text-[12px] font-light text-muted">{{ info.tags.lyrics ? t('extractTags.hasLyrics') : t('extractTags.noLyrics') }}</span></span>
        </label>

        <div class="flex justify-end gap-2">
          <button type="button" class="h-11 rounded-full px-5 text-[15px] text-muted hover:text-ink" @click="emit('close')">{{ t('common.cancel') }}</button>
          <button type="button" class="h-11 rounded-full bg-ink px-6 text-[15px] text-on-ink disabled:opacity-50" :disabled="!!busy || !form.title.trim()" @click="save">
            {{ busy === 'save' ? t('extractTags.saving') : t('common.save') }}
          </button>
        </div>
      </template>
    </div>
  </BaseModal>
</template>
