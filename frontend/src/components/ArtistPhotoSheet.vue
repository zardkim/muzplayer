<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { Search } from '@lucide/vue'
import { api } from '../api'
import { errorMessage } from '../i18n'
import { useUi } from '../stores/ui'
import type { ArtistDetail, ArtistImageCandidate } from '../types'
import BaseModal from './BaseModal.vue'

// Admin: pick the artist's photo from Wikipedia articles (Korean, then English), or remove it.
const props = defineProps<{ artist: ArtistDetail }>()
const emit = defineEmits<{ close: []; changed: [] }>()
const { t } = useI18n()
const ui = useUi()
const q = ref(props.artist.name)
const items = ref<ArtistImageCandidate[]>([])
const loading = ref(false)
const busy = ref(false)
const error = ref('')

async function find() {
  loading.value = true
  error.value = ''
  try {
    items.value = (await api<{ items: ArtistImageCandidate[] }>(`/admin/artists/${props.artist.id}/image-candidates?q=${encodeURIComponent(q.value.trim())}`)).items
  } catch (e) {
    error.value = errorMessage(e)
  } finally {
    loading.value = false
  }
}
onMounted(find)

async function pick(c: ArtistImageCandidate) {
  busy.value = true
  try {
    await api(`/admin/artists/${props.artist.id}/image`, { method: 'PUT', body: c })
    ui.notify(t('common.saved'))
    emit('changed')
  } catch (e) {
    ui.notify(errorMessage(e), true)
  } finally {
    busy.value = false
  }
}

async function remove() {
  busy.value = true
  try {
    await api(`/admin/artists/${props.artist.id}/image`, { method: 'DELETE' })
    emit('changed')
  } catch (e) {
    ui.notify(errorMessage(e), true)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <BaseModal :title="t('artists.photoTitle')" @close="emit('close')">
    <div class="flex flex-col gap-4">
      <p class="text-[14px] font-light text-muted">{{ t('artists.photoHelp') }}</p>
      <form class="flex gap-2" @submit.prevent="find">
        <input v-model="q" maxlength="200" class="h-11 min-w-0 flex-1 rounded-full bg-surface px-4 text-[15px] outline-none focus:ring-2 focus:ring-ink" :aria-label="t('search.label')" />
        <button type="submit" class="grid size-11 flex-none place-items-center rounded-full bg-ink text-on-ink" :aria-label="t('search.label')"><Search :size="18" /></button>
      </form>
      <p v-if="loading" class="text-[14px] text-muted">{{ t('common.loading') }}</p>
      <p v-else-if="error" class="text-[14px] text-danger">{{ error }}</p>
      <p v-else-if="!items.length" class="text-[14px] text-muted">{{ t('artists.photoNone') }}</p>
      <ul v-else class="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <li v-for="c in items" :key="`${c.wiki}:${c.title}`">
          <button type="button" class="group flex w-full flex-col gap-1.5 text-left disabled:opacity-50" :disabled="busy" @click="pick(c)">
            <img :src="c.image" alt="" loading="lazy" referrerpolicy="no-referrer" class="aspect-square w-full rounded-xl object-cover object-[50%_30%] ring-accent transition group-hover:ring-2" />
            <span class="truncate text-[14px]">{{ c.title }}</span>
            <span class="line-clamp-2 text-[12px] font-light text-muted">{{ c.wiki.toUpperCase() }} · {{ c.description || '—' }}</span>
          </button>
        </li>
      </ul>
      <button v-if="artist.image_v" type="button" class="self-start text-[14px] text-danger underline disabled:opacity-50" :disabled="busy" @click="remove">{{ t('artists.photoRemove') }}</button>
    </div>
  </BaseModal>
</template>
