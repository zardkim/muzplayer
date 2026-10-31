<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api'
import { appConfig } from '../config'
import { errorMessage } from '../i18n'
import { install, installPrompt, isIos, isStandalone } from '../pwa'
import { useAuth } from '../stores/auth'
import { SKIPS, usePlayer } from '../stores/player'
import { CACHE_SIZES, PREFETCH_COUNTS, useUi } from '../stores/ui'
import { cacheUsage, clearAudioCache } from '../audioCache'
import HomeSectionsEditor from '../components/HomeSectionsEditor.vue'
import LanguageSwitch from '../components/LanguageSwitch.vue'
import ThemeSwitch from '../components/ThemeSwitch.vue'
import SelectRow from '../components/SelectRow.vue'
import ToggleRow from '../components/ToggleRow.vue'
import PageHeader from '../components/PageHeader.vue'

const { t } = useI18n()
const auth = useAuth()
const ui = useUi()
const player = usePlayer()
const version = (window as unknown as { __MUZ_VERSION__?: string }).__MUZ_VERSION__ ?? ''
const current = ref('')
const next = ref('')
const confirmNext = ref('')
const error = ref('')

async function changePassword() {
  error.value = ''
  if (next.value !== confirmNext.value) {
    error.value = t('settings.mismatch')
    return
  }
  try {
    await api('/auth/password', { method: 'PUT', body: { current_password: current.value, new_password: next.value } })
    current.value = next.value = confirmNext.value = ''
    ui.notify(t('settings.changed'))
  } catch (e) {
    error.value = errorMessage(e)
  }
}
const counts = PREFETCH_COUNTS.map((n) => ({ value: n, label: n ? t('settings.songsN', n) : t('settings.off') }))
const sizes = CACHE_SIZES.map((mb) => ({ value: mb, label: mb >= 1024 ? `${mb / 1024} GB` : `${mb} MB` }))
const albumEnds = (['radio', 'artist', 'stop'] as const).map((v) => ({ value: v, label: t(`settings.albumEnd_${v}`) }))
const used = ref(cacheUsage())
async function clearCache() {
  await clearAudioCache()
  used.value = cacheUsage()
  ui.notify(t('settings.cacheCleared'))
}
const mb = (bytes: number) => (bytes / 1024 / 1024).toFixed(bytes < 10 * 1024 * 1024 ? 1 : 0)

// kept on the server: the same on every device
const recordHistory = computed({
  get: () => auth.user?.record_history ?? true,
  set: (v: boolean) => {
    auth.updateSettings({ record_history: v }).catch((e) => ui.notify(errorMessage(e), true))
  },
})
const field = 'h-12 rounded-full bg-surface px-4 text-base text-ink outline-none focus:ring-2 focus:ring-ink'
</script>

<template>
  <div class="flex max-w-lg flex-col gap-9">
    <PageHeader :title="t('settings.title')" />

    <section class="flex flex-col gap-3">
      <h2 class="text-[22px] font-bold">{{ t('settings.display') }}</h2>
      <h3 class="font-medium">{{ t('settings.theme') }}</h3>
      <ThemeSwitch />
      <h3 class="mt-2 font-medium">{{ t('settings.language') }}</h3>
      <LanguageSwitch />
      <div class="mt-2 flex flex-col divide-y divide-line">
        <ToggleRow v-model="ui.playerPrefs.showYear" :title="t('settings.showYear')" :hint="t('settings.showYearHelp')" />
        <ToggleRow v-model="ui.playerPrefs.showCodec" :title="t('settings.showCodec')" :hint="t('settings.showCodecHelp')" />
        <ToggleRow v-model="ui.playerPrefs.showQuality" :title="t('settings.showQuality')" :hint="t('settings.showQualityHelp')" />
        <ToggleRow v-model="ui.playerPrefs.showPopular" :title="t('settings.showPopular')" :hint="t('settings.showPopularHelp')" />
        <div class="hidden md:block"><ToggleRow v-model="ui.playerPrefs.showVolume" :title="t('settings.showVolume')" :hint="t('settings.showVolumeHelp')" /></div>
      </div>
    </section>

    <section class="flex flex-col gap-1">
      <h2 class="text-[22px] font-bold">{{ t('settings.homeScreen') }}</h2>
      <p class="text-[13px] font-light text-muted">{{ t('settings.homeScreenHelp') }}</p>
      <HomeSectionsEditor />
    </section>

    <section class="flex flex-col gap-1">
      <h2 class="text-[22px] font-bold">{{ t('settings.player') }}</h2>
      <div class="flex flex-col divide-y divide-line">
        <ToggleRow v-model="ui.playerPrefs.openOnPlay" :title="t('settings.openOnPlay')" :hint="t('settings.openOnPlayHelp')" />
        <ToggleRow v-model="ui.playerPrefs.keepAwake" :title="t('settings.keepAwake')" :hint="t('settings.keepAwakeHelp')" />
        <ToggleRow v-model="ui.playerPrefs.musicSpeed" :title="t('settings.musicSpeed')" :hint="t('settings.musicSpeedHelp')" />
        <ToggleRow v-model="recordHistory" :title="t('settings.recordHistory')" :hint="t('settings.recordHistoryHelp')" />
      </div>
    </section>

    <section class="flex flex-col gap-1">
      <h2 class="text-[22px] font-bold">{{ t('settings.autoplay') }}</h2>
      <div class="flex flex-col divide-y divide-line">
        <ToggleRow v-model="ui.playerPrefs.autoplay" :title="t('settings.autoplayOn')" :hint="t('settings.autoplayHelp')" />
        <SelectRow v-model="ui.playerPrefs.albumEnd" :title="t('settings.albumEnd')" :hint="t('settings.albumEndHelp')" :options="albumEnds" />
      </div>
    </section>

    <section class="flex flex-col gap-1">
      <h2 class="text-[22px] font-bold">{{ t('settings.storage') }}</h2>
      <div class="flex flex-col divide-y divide-line">
        <SelectRow v-model="ui.playerPrefs.prefetchWifi" :title="t('settings.prefetchWifi')" :hint="t('settings.prefetchWifiHelp')" :options="counts" />
        <SelectRow v-model="ui.playerPrefs.prefetchCellular" :title="t('settings.prefetchCellular')" :hint="t('settings.prefetchCellularHelp')" :options="counts" />
        <SelectRow v-model="ui.playerPrefs.cacheMB" :title="t('settings.cacheSize')" :hint="t('settings.cacheSizeHelp')" :options="sizes" />
      </div>
      <div class="mt-2 flex items-center gap-4">
        <span class="flex-1 text-[14px] font-light text-muted">{{ t('settings.cacheUsed', { mb: mb(used) }) }}</span>
        <button type="button" class="h-10 rounded-full border border-line-strong px-4 text-[14px] hover:border-ink" @click="clearCache">{{ t('settings.clearCache') }}</button>
      </div>
    </section>

    <section v-if="appConfig.audiobooks" class="flex flex-col gap-3">
      <h2 class="text-[22px] font-bold">{{ t('settings.audiobooks') }}</h2>
      <div class="flex flex-wrap gap-4">
        <label class="flex items-center gap-2.5 text-[15px]">
          {{ t('settings.skipBack') }}
          <select v-model.number="player.skipBack" class="h-10 rounded-full border border-line-strong bg-bg px-3 text-sm">
            <option v-for="s in SKIPS" :key="s" :value="s">{{ t('settings.seconds', { n: s }) }}</option>
          </select>
        </label>
        <label class="flex items-center gap-2.5 text-[15px]">
          {{ t('settings.skipForward') }}
          <select v-model.number="player.skipForward" class="h-10 rounded-full border border-line-strong bg-bg px-3 text-sm">
            <option v-for="s in SKIPS" :key="s" :value="s">{{ t('settings.seconds', { n: s }) }}</option>
          </select>
        </label>
      </div>
      <p class="text-[13px] font-light text-muted">{{ t('settings.audiobooksHelp') }}</p>
    </section>

    <section class="flex flex-col gap-3">
      <h2 class="text-[22px] font-bold">{{ t('settings.installTitle') }}</h2>
      <p v-if="isStandalone" class="font-light text-muted">{{ t('settings.installed') }}</p>
      <button v-else-if="installPrompt" type="button" class="h-11 self-start rounded-full bg-ink px-5 text-[15px] text-on-ink" @click="install">{{ t('settings.installApp') }}</button>
      <p v-else-if="isIos" class="font-light text-muted">{{ t('settings.installIos') }}</p>
    </section>

    <section class="flex flex-col gap-3">
      <h2 class="text-[22px] font-bold">{{ t('settings.account') }}</h2>
      <p class="font-light text-muted">{{ auth.user?.display_name }} · {{ auth.user?.username }}</p>
      <form class="flex flex-col gap-3" @submit.prevent="changePassword">
        <h3 class="mt-2 font-medium">{{ t('settings.changePassword') }}</h3>
        <label class="flex flex-col gap-1.5 text-[13px] text-muted">{{ t('settings.currentPassword') }}<input v-model="current" type="password" autocomplete="current-password" required :class="field" /></label>
        <label class="flex flex-col gap-1.5 text-[13px] text-muted">{{ t('settings.newPassword') }}<input v-model="next" type="password" autocomplete="new-password" minlength="8" required :class="field" /></label>
        <label class="flex flex-col gap-1.5 text-[13px] text-muted">{{ t('settings.confirmPassword') }}<input v-model="confirmNext" type="password" autocomplete="new-password" minlength="8" required :class="field" /></label>
        <p v-if="error" role="alert" class="text-[13px] text-danger">{{ error }}</p>
        <button type="submit" class="h-11 self-start rounded-full bg-ink px-6 text-[15px] text-on-ink">{{ t('common.save') }}</button>
      </form>
    </section>

    <p v-if="version" class="font-display text-xs text-muted">{{ t('settings.version', { v: version }) }}</p>
  </div>
</template>
