<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Disc3, ListPlus, MicVocal, MonitorPlay } from '@lucide/vue'
import { coverGlow } from '../coverColor'
import { errorMessage } from '../i18n'
import { useLibrary } from '../stores/library'
import { usePlayer } from '../stores/player'
import { useUi } from '../stores/ui'
import CoverArt from '../components/CoverArt.vue'
import LikeButton from '../components/LikeButton.vue'
import LyricsPanel from '../components/LyricsPanel.vue'
import PageHeader from '../components/PageHeader.vue'
import QueueList from '../components/QueueList.vue'
import StarRating from '../components/StarRating.vue'

// PC player: a page inside the sidebar and bars (the bottom bar keeps the controls). The song up top,
// below it the lyrics and the queue side by side; narrower windows show one of them, as tabs.
const { t } = useI18n()
const player = usePlayer()
const library = useLibrary()
const ui = useUi()
const glow = ref('#C9D6E3')

watch(
  () => [player.current?.album_id, player.current?.cover_v] as const,
  async ([albumId, v]) => {
    glow.value = '#C9D6E3'
    if (albumId && player.current?.has_cover) glow.value = (await coverGlow(albumId, v)) ?? glow.value
  },
  { immediate: true },
)

async function rate(stars: number | null) {
  if (!player.current) return
  try {
    await library.rate(player.current, stars)
  } catch (e) {
    ui.notify(errorMessage(e), true)
  }
}

function videos() {
  const tr = player.current
  if (tr) ui.videoTarget = { trackId: tr.id, title: tr.title, artist: tr.artist }
}
</script>

<template>
  <div v-if="!player.current || player.mode !== 'music'" class="flex flex-col gap-6">
    <PageHeader :title="t('player.nowPlaying')" />
    <p class="font-light text-muted">{{ t('player.notPlaying') }}</p>
  </div>

  <div v-else class="flex flex-col gap-6">
    <!-- the song -->
    <section
      class="relative flex items-end gap-8 overflow-hidden rounded-3xl p-6 lg:p-8"
      :style="{ background: `linear-gradient(120deg, color-mix(in srgb, ${glow} 55%, white) 0%, color-mix(in srgb, ${glow} 18%, white) 100%)` }"
    >
      <CoverArt
        :album-id="player.current.album_id"
        :has-cover="player.current.has_cover"
        :version="player.current.cover_v"
        size="large"
        rounded="rounded-2xl"
        class="w-[clamp(140px,22vh,260px)] flex-none shadow-[0_18px_44px_rgba(17,17,19,0.22)]"
      />
      <div class="flex min-w-0 flex-1 flex-col gap-4 pb-1">
        <div class="flex min-w-0 flex-col gap-1">
          <span class="text-[12px] font-medium uppercase tracking-[0.18em] text-[#52525B]">{{ t('player.nowPlaying') }}</span>
          <h1 class="line-clamp-2 text-[32px] font-extrabold leading-tight tracking-tight lg:text-[44px]">{{ player.current.title }}</h1>
          <span class="flex min-w-0 flex-wrap items-center gap-x-2 text-[17px] text-[#3F3F46]">
            <RouterLink v-if="player.current.artist_id" :to="{ name: 'artist', params: { id: player.current.artist_id } }" class="truncate font-medium hover:underline">{{ player.current.artist }}</RouterLink>
            <span v-else class="truncate font-medium">{{ player.current.artist || t('common.unknownArtist') }}</span>
            <template v-if="player.current.album_id && player.current.album_kind !== 'chart' && player.current.album">
              <span aria-hidden="true">·</span>
              <RouterLink :to="{ name: 'album', params: { id: player.current.album_id } }" class="truncate font-light hover:underline">{{ player.current.album }}</RouterLink>
            </template>
            <span class="rounded border border-black/15 px-1.5 text-[11px] uppercase tracking-wide">{{ player.current.format }}</span>
          </span>
        </div>
        <div class="flex flex-wrap items-center gap-x-4 gap-y-2">
          <LikeButton :track="player.current" :size="24" box="size-11 bg-white/60" />
          <StarRating :value="library.rating(player.current)" :size="20" @rate="rate" />
          <span class="flex items-center gap-1">
            <button type="button" class="grid size-10 place-items-center rounded-full hover:bg-white/70" :aria-label="t('common.addToPlaylist')" :title="t('common.addToPlaylist')" @click="ui.playlistPicker = [player.current]">
              <ListPlus :size="21" :stroke-width="1.3" />
            </button>
            <button type="button" class="grid size-10 place-items-center rounded-full hover:bg-white/70" :class="player.current.has_video ? '' : 'text-muted'" :aria-label="t('common.watchVideos')" :title="t('common.watchVideos')" @click="videos">
              <MonitorPlay :size="20" :stroke-width="1.3" />
            </button>
            <RouterLink v-if="player.current.album_id && player.current.album_kind !== 'chart'" :to="{ name: 'album', params: { id: player.current.album_id } }" class="grid size-10 place-items-center rounded-full hover:bg-white/70" :aria-label="t('common.goToAlbum')" :title="t('common.goToAlbum')">
              <Disc3 :size="20" :stroke-width="1.3" />
            </RouterLink>
            <RouterLink v-if="player.current.artist_id" :to="{ name: 'artist', params: { id: player.current.artist_id } }" class="grid size-10 place-items-center rounded-full hover:bg-white/70" :aria-label="t('common.goToArtist')" :title="t('common.goToArtist')">
              <MicVocal :size="20" :stroke-width="1.3" />
            </RouterLink>
          </span>
        </div>
      </div>
    </section>

    <!-- lyrics and the queue: side by side on wide windows, tabs below xl -->
    <div class="flex gap-1 xl:hidden" role="tablist">
      <button
        v-for="tab in (['lyrics', 'queue'] as const)"
        :key="tab"
        type="button"
        role="tab"
        class="h-10 rounded-full px-5 text-[15px] transition-colors"
        :class="ui.playerTab === tab ? 'bg-ink text-white' : 'bg-surface hover:bg-surface-2'"
        :aria-selected="ui.playerTab === tab"
        @click="ui.playerTab = tab"
      >
        {{ tab === 'lyrics' ? t('player.lyrics') : t('player.queue') }}
      </button>
    </div>
    <!-- sized to fill the window under the song (top bar, page padding and the bottom bar taken off) -->
    <div class="grid h-[max(340px,calc(100dvh-22vh-460px))] grid-rows-[minmax(0,1fr)] gap-6 xl:h-[max(340px,calc(100dvh-22vh-396px))] xl:grid-cols-[minmax(0,1fr)_minmax(320px,400px)]">
      <section class="min-h-0 flex-col rounded-3xl bg-surface py-2" :class="ui.playerTab === 'lyrics' ? 'flex' : 'hidden xl:flex'" :aria-label="t('player.lyrics')">
        <h2 class="hidden px-6 pt-4 text-[17px] font-bold xl:block">{{ t('player.lyrics') }}</h2>
        <LyricsPanel large class="min-h-0 flex-1 px-6" />
      </section>
      <section class="min-h-0 flex-col rounded-3xl bg-surface p-2" :class="ui.playerTab === 'queue' ? 'flex' : 'hidden xl:flex'" :aria-label="t('player.queue')">
        <div class="flex flex-none items-center justify-between px-4 pb-2 pt-4">
          <h2 class="hidden text-[17px] font-bold xl:block">{{ t('player.queue') }}</h2>
          <button
            v-if="player.queue.length > player.index + 1"
            type="button"
            class="ml-auto h-9 rounded-full border border-line-strong px-3 text-[13px] hover:bg-bg"
            @click="player.clearUpcoming()"
          >
            {{ t('player.clearQueue') }}
          </button>
        </div>
        <QueueList class="min-h-0 flex-1 overflow-y-auto px-2 pb-2" />
      </section>
    </div>
  </div>
</template>
