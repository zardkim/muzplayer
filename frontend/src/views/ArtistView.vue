<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { Camera, Link2, PencilLine } from '@lucide/vue'
import { api } from '../api'
import { errorMessage } from '../i18n'
import { useAuth } from '../stores/auth'
import type { ArtistDetail } from '../types'
import AlbumGrid from '../components/AlbumGrid.vue'
import ArtistPhoto from '../components/ArtistPhoto.vue'
import AliasesSheet from '../components/AliasesSheet.vue'
import BugsLinkSheet from '../components/BugsLinkSheet.vue'
import ArtistPhotoSheet from '../components/ArtistPhotoSheet.vue'
import PlayActions from '../components/PlayActions.vue'
import TrackList from '../components/TrackList.vue'
import SectionTitle from '../components/SectionTitle.vue'
import Marquee from '../components/Marquee.vue'

const props = defineProps<{ id: string }>()
const { t } = useI18n()
const auth = useAuth()
const photoSheet = ref(false)
const aliasSheet = ref(false)
const bugsSheet = ref(false)
// what Bugs says of it: 그룹 (여성) · 대한민국 · 2015 · 댄스/팝
const bugsLine = computed(() => {
  const b = artist.value?.bugs
  return b?.id ? [b.type, b.country, b.debut && t('bugs.debut', { year: b.debut }), b.genre].filter(Boolean).join(' · ') : ''
})
const artist = ref<ArtistDetail | null>(null)
const error = ref('')

const official = computed(() => artist.value?.albums.filter((a) => a.kind !== 'unofficial') ?? [])
const unofficial = computed(() => artist.value?.albums.filter((a) => a.kind === 'unofficial') ?? [])

async function load() {
  try {
    artist.value = await api<ArtistDetail>(`/artists/${props.id}`)
  } catch (e) {
    error.value = errorMessage(e)
  }
}
onMounted(load)

function photoChanged() {
  photoSheet.value = false
  load()
}
</script>

<template>
  <p v-if="error" class="font-light text-muted">{{ error }}</p>
  <div v-else-if="artist" class="flex flex-col gap-8">
    <header class="flex flex-col items-center gap-5 text-center md:flex-row md:items-end md:gap-8 md:text-left">
      <div class="relative w-44 flex-none md:w-56">
        <ArtistPhoto :artist-id="artist.id" :name="artist.name" :version="artist.image_v" size="large" class="shadow-[0_16px_40px_rgba(17,17,19,0.18)]" />
        <button
          v-if="auth.user?.is_admin"
          type="button"
          class="absolute bottom-1 right-1 grid size-10 place-items-center rounded-full bg-bg/90 shadow hover:bg-bg"
          :aria-label="t('artists.photoTitle')"
          :title="t('artists.photoTitle')"
          @click="photoSheet = true"
        >
          <Camera :size="18" :stroke-width="1.6" />
        </button>
      </div>
      <div class="flex min-w-0 flex-col gap-3 md:pb-2">
        <span class="text-[13px] font-medium uppercase tracking-[0.14em] text-muted">{{ t('artists.label') }}</span>
        <Marquee as="h1" :text="artist.name" class="text-[32px] font-bold leading-tight md:text-[44px]" />
        <!-- its other names (a search in any of them finds it); an admin edits them -->
        <span v-if="artist.aliases?.length || auth.user?.is_admin" class="-mt-1.5 flex items-center justify-center gap-1 text-[14px] font-light text-muted md:justify-start">
          <span v-if="artist.aliases?.length" class="line-clamp-2">{{ t('aliases.shown', { names: artist.aliases.join(' · ') }) }}</span>
          <button v-if="auth.user?.is_admin" type="button" class="flex h-8 flex-none items-center gap-1 rounded-full px-2 hover:bg-surface hover:text-ink" :aria-label="t('aliases.title')" :title="t('aliases.title')" @click="aliasSheet = true">
            <PencilLine :size="14" :stroke-width="1.6" /><span v-if="!artist.aliases?.length">{{ t('aliases.title') }}</span>
          </button>
        </span>
        <!-- Bugs: solo or group, country, debut; an admin links it -->
        <span v-if="bugsLine || auth.user?.is_admin" class="-mt-1.5 flex items-center justify-center gap-1 text-[14px] font-light text-muted md:justify-start">
          <a v-if="bugsLine" :href="artist.bugs!.url!" target="_blank" rel="noopener" class="hover:text-ink hover:underline">{{ bugsLine }}</a>
          <button v-if="auth.user?.is_admin" type="button" class="flex h-8 flex-none items-center gap-1 rounded-full px-2 hover:bg-surface hover:text-ink" :aria-label="t('bugs.linkTitle')" :title="t('bugs.linkTitle')" @click="bugsSheet = true">
            <Link2 :size="14" :stroke-width="1.6" /><span v-if="!bugsLine">{{ artist.bugs?.source === 'unsure' ? t('bugs.unsure') : artist.bugs?.source === 'none' ? t('bugs.none') : t('bugs.linkTitle') }}</span>
          </button>
        </span>
        <span v-if="artist.tag_name && artist.tag_name !== artist.name" class="-mt-1.5 text-[13px] font-light text-subtle">{{ t('bugs.tagged', { name: artist.tag_name }) }}</span>
        <span class="text-[15px] font-light text-muted">
          <template v-if="artist.albums.length">{{ t('common.albums', artist.albums.length) }} · </template>{{ t('common.tracks', artist.tracks.length) }}
        </span>
        <div v-if="artist.tracks.length" class="flex flex-wrap justify-center gap-2 md:justify-start">
          <PlayActions :tracks="artist.tracks" large />
        </div>
        <a v-if="artist.image_credit" :href="artist.image_credit.url" target="_blank" rel="noopener noreferrer" class="text-[12px] font-light text-subtle hover:text-muted hover:underline">
          {{ t('artists.photoCredit', { title: artist.image_credit.title }) }}
        </a>
      </div>
    </header>
    <!-- a group's members, a singer's groups (Bugs): ours are links -->
    <section v-for="part in (['members', 'groups'] as const)" v-show="artist.bugs?.[part]?.length" :key="part" class="flex flex-col gap-3">
      <SectionTitle :title="t(`bugs.${part}`)" />
      <div class="flex flex-wrap gap-2">
        <template v-for="m in artist.bugs?.[part] ?? []" :key="m.bugs_id">
          <RouterLink v-if="m.id" :to="{ name: 'artist', params: { id: m.id } }" class="flex h-10 items-center rounded-full border border-line-strong px-4 text-[15px] hover:border-ink">{{ m.name }}</RouterLink>
          <span v-else class="flex h-10 items-center rounded-full bg-surface px-4 text-[15px] font-light text-muted">{{ m.name }}</span>
        </template>
      </div>
    </section>
    <BugsLinkSheet v-if="bugsSheet" :artist="artist" @close="bugsSheet = false" @changed="(a) => (artist = a)" />
    <AliasesSheet v-if="aliasSheet" :artist="artist" @close="aliasSheet = false" @changed="(names, entries) => artist && ((artist.aliases = names), (artist.alias_entries = entries))" />
    <ArtistPhotoSheet v-if="photoSheet" :artist="artist" @close="photoSheet = false" @changed="photoChanged" />
    <section v-if="official.length" class="flex flex-col gap-4">
      <SectionTitle :title="t('artists.albums')" />
      <AlbumGrid :albums="official" />
    </section>
    <section v-if="unofficial.length" class="flex flex-col gap-4">
      <SectionTitle :title="t('artists.unofficial')" />
      <AlbumGrid :albums="unofficial" />
    </section>
    <section v-if="artist.tracks.length" class="flex flex-col gap-1">
      <SectionTitle :title="t('artists.tracks')" />
      <TrackList :tracks="artist.tracks" />
    </section>
    <section v-if="artist.featured?.length" class="flex flex-col gap-4">
      <SectionTitle :title="t('artists.featured')" />
      <TrackList :tracks="artist.featured" show-album />
    </section>
  </div>
</template>
