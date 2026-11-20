<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { AudioLines, BookHeadphones, Check, ChevronRight, Download, ExternalLink, HardDrive, House, Info, MonitorSmartphone, Play, Radio, Smartphone, Sparkles, User } from '@lucide/vue'
import { api } from '../api'
import { appConfig } from '../config'
import { errorMessage } from '../i18n'
import { install, installPrompt, isAndroid, isIos, isStandalone, isWindows } from '../pwa'
import { native } from '../native'
import { useAuth } from '../stores/auth'
import { SKIPS, usePlayer } from '../stores/player'
import { APP_ICONS, CACHE_SIZES, CROSSFADES, PREFETCH_COUNTS, useUi } from '../stores/ui'
import { cacheUsage, clearAudioCache } from '../audioCache'
import { canSave, savedBytes } from '../offline'
import { QUALITIES } from '../stream'
import { clearPlayerLog, readPlayerLog } from '../playerLog'
import EqualizerEditor from '../components/EqualizerEditor.vue'
import HomeSectionsEditor from '../components/HomeSectionsEditor.vue'
import LanguageSwitch from '../components/LanguageSwitch.vue'
import TasteCard from '../components/TasteCard.vue'
import ThemeSwitch from '../components/ThemeSwitch.vue'
import SelectRow from '../components/SelectRow.vue'
import ToggleRow from '../components/ToggleRow.vue'
import PageHeader from '../components/PageHeader.vue'
import AppLogo from '../components/AppLogo.vue'

// Settings: a menu of its parts, each on its own screen (/settings/<part>). Wide screens show the
// menu beside the open part (the first one when none is picked).
const props = defineProps<{ section?: string }>()
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
const levelings = (['off', 'track', 'album'] as const).map((v) => ({ value: v, label: t(`settings.leveling_${v}`) }))
const fades = CROSSFADES.map((s) => ({ value: s, label: s ? t('settings.seconds', { n: s }) : t('settings.off') }))
const qualities = QUALITIES.map((q) => ({ value: q, label: q === 'orig' ? t('settings.quality_orig') : `${q} kbps` }))
const albumEnds = (['radio', 'artist', 'stop'] as const).map((v) => ({ value: v, label: t(`settings.albumEnd_${v}`) }))
const used = ref(cacheUsage())
async function clearCache() {
  await clearAudioCache()
  used.value = cacheUsage()
  ui.notify(t('settings.cacheCleared'))
}
// Player → playback log (playerLog.ts): to send along when a call or the lock screen misbehaves
const playerLog = ref('')
const logCopied = ref(false)
async function copyLog() {
  const text = `muzplayer ${version} ${navigator.userAgent}\n${readPlayerLog()}`
  try {
    await navigator.clipboard.writeText(text)
    logCopied.value = true
    window.setTimeout(() => (logCopied.value = false), 2000)
  } catch {
    ui.notify(t('settings.playerLogCopyFailed'), true)
  }
}
function clearLog() {
  clearPlayerLog()
  playerLog.value = ''
}
const mb = (bytes: number) => (bytes / 1024 / 1024).toFixed(bytes < 10 * 1024 * 1024 ? 1 : 0)

// kept on the server: the same on every device
const recordHistory = computed({
  get: () => auth.user?.record_history ?? true,
  set: (v: boolean) => {
    auth.updateSettings({ record_history: v }).catch((e) => ui.notify(errorMessage(e), true))
  },
})
const field = 'field h-12 px-4'
const sections = computed(() => [
  { key: 'display', title: 'settings.display', hint: 'settings.menu_display', icon: MonitorSmartphone },
  { key: 'home', title: 'settings.homeScreen', hint: 'settings.menu_home', icon: House },
  { key: 'player', title: 'settings.player', hint: 'settings.menu_player', icon: Play },
  { key: 'sound', title: 'settings.sound', hint: 'settings.menu_sound', icon: AudioLines },
  { key: 'autoplay', title: 'settings.autoplay', hint: 'settings.menu_autoplay', icon: Radio },
  { key: 'taste', title: 'settings.taste', hint: 'settings.menu_taste', icon: Sparkles },
  { key: 'storage', title: 'settings.storage', hint: 'settings.menu_storage', icon: HardDrive },
  ...(appConfig.audiobooks ? [{ key: 'audiobooks', title: 'settings.audiobooks', hint: 'settings.menu_audiobooks', icon: BookHeadphones }] : []),
  { key: 'install', title: 'settings.installTitle', hint: 'settings.menu_install', icon: Smartphone },
  { key: 'account', title: 'settings.account', hint: 'settings.menu_account', icon: User },
  { key: 'about', title: 'settings.about', hint: 'settings.menu_about', icon: Info },
])
const open = computed(() => sections.value.find((x) => x.key === props.section) ?? null)

// add to home screen, on a PC: the Windows app's installer (its latest release); in the app, a newer one
const winApp = ref<{ page: string; version: string | null; url: string | null; size: number | null } | null>(null)
onMounted(() => {
  if (isWindows) api<NonNullable<typeof winApp.value>>('/apps/windows').then((r) => (winApp.value = r)).catch(() => {})
})
const newer = (a: string, b: string) => {
  const x = a.split('.').map(Number), y = b.split('.').map(Number)
  for (let i = 0; i < 3; i++) if ((x[i] || 0) !== (y[i] || 0)) return (x[i] || 0) > (y[i] || 0)
  return false
}
const winUpdate = computed(() => !!(native && winApp.value?.version && newer(winApp.value.version, native.version)))
// in the app (0.3.0 and later): it downloads the installer itself, installs it and starts again;
// an older app only gets the download link
const updating = ref<number | null>(null)
const updateError = ref('')
async function updateApp() {
  if (!native?.update || !winApp.value?.url) return
  updateError.value = ''
  updating.value = 0
  native.onUpdateProgress?.((f) => (updating.value = f))
  const r = await native.update(winApp.value.url).catch(() => ({ ok: false, error: 'download' }))
  if (!r.ok) {
    updating.value = null
    updateError.value = t('settings.windowsUpdateFailed')
  }
}
// on a phone: the home screen icon (index.html takes it when the app is added)
const phone = isIos || isAndroid
const iconFile = (v: string) => (v === 'auto' || v === 'light' ? '/icon-180.png' : `/icon-${v}-180.png`)
const shown = computed(() => open.value?.key ?? 'display') // the part a wide screen shows
// about: where the source, its licence and the releases are
const REPO = 'https://github.com/zardkim/muzplayer'
const aboutLinks = [
  { label: 'settings.aboutSource', href: REPO },
  { label: 'settings.aboutReleases', href: `${REPO}/releases` },
  { label: 'settings.aboutLicense', href: `${REPO}/blob/main/LICENSE` },
  { label: 'settings.aboutNotices', href: `${REPO}/blob/main/THIRD_PARTY_NOTICES.md` },
  { label: 'settings.aboutIssues', href: `${REPO}/issues` },
  { label: 'settings.aboutDocker', href: 'https://hub.docker.com/r/zardkim/muzplayer' },
]
</script>

<template>
  <div class="flex flex-col gap-7">
    <!-- phone: the open part's name (back goes to the menu); wide screens: Settings over both -->
    <PageHeader v-if="open" :title="t(open.title)" :icon="open.icon" class="md:hidden" />
    <PageHeader :title="t('settings.title')" :class="open ? 'hidden md:flex' : ''" />

    <div class="flex flex-col gap-8 md:flex-row md:items-start md:gap-12">
      <nav :aria-label="t('settings.title')" class="flex-col md:sticky md:top-0 md:flex md:w-60 md:flex-none" :class="open ? 'hidden' : 'flex'">
        <RouterLink
          v-for="x in sections"
          :key="x.key"
          :to="{ name: 'settings', params: { section: x.key } }"
          :replace="!!open"
          class="flex min-h-[64px] items-center gap-4 border-b border-surface md:min-h-0 md:rounded-xl md:border-0 md:px-3 md:py-2.5"
          :class="shown === x.key ? 'md:bg-surface' : 'md:hover:bg-surface'"
          :aria-current="shown === x.key ? 'page' : undefined"
        >
          <component :is="x.icon" :size="22" :stroke-width="1.4" class="flex-none text-muted" />
          <span class="flex min-w-0 flex-1 flex-col">
            <span class="text-[17px] md:text-[15px]" :class="shown === x.key ? 'md:font-medium' : ''">{{ t(x.title) }}</span>
            <span class="truncate text-[13px] font-light text-muted md:hidden">{{ t(x.hint) }}</span>
          </span>
          <ChevronRight :size="18" class="flex-none text-subtle md:hidden" />
        </RouterLink>
        <p v-if="version" class="mt-5 font-display text-xs text-muted md:px-3">{{ t('settings.version', { v: version }) }}</p>
      </nav>

      <div class="min-w-0 max-w-lg flex-1 flex-col gap-9" :class="open ? 'flex' : 'hidden md:flex'">
        <section v-if="shown === 'display'" class="flex flex-col gap-3">
          <h2 class="hidden text-[22px] font-bold md:block">{{ t('settings.display') }}</h2>
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

        <section v-if="shown === 'taste'" class="flex flex-col gap-3">
          <h2 class="hidden text-[22px] font-bold md:block">{{ t('settings.taste') }}</h2>
          <TasteCard />
        </section>

        <section v-if="shown === 'home'" class="flex flex-col gap-1">
          <h2 class="hidden text-[22px] font-bold md:block">{{ t('settings.homeScreen') }}</h2>
          <p class="text-[13px] font-light text-muted">{{ t('settings.homeScreenHelp') }}</p>
          <HomeSectionsEditor />
        </section>

        <section v-if="shown === 'player'" class="flex flex-col gap-1">
          <h2 class="hidden text-[22px] font-bold md:block">{{ t('settings.player') }}</h2>
          <div class="flex flex-col divide-y divide-line">
            <ToggleRow v-model="ui.playerPrefs.openOnPlay" :title="t('settings.openOnPlay')" :hint="t('settings.openOnPlayHelp')" />
            <ToggleRow v-model="ui.playerPrefs.startMinimized" :title="t('settings.startMinimized')" :hint="t('settings.startMinimizedHelp')" />
            <ToggleRow v-model="ui.playerPrefs.keepAwake" :title="t('settings.keepAwake')" :hint="t('settings.keepAwakeHelp')" />
            <ToggleRow v-model="ui.playerPrefs.musicSpeed" :title="t('settings.musicSpeed')" :hint="t('settings.musicSpeedHelp')" />
            <ToggleRow v-model="recordHistory" :title="t('settings.recordHistory')" :hint="t('settings.recordHistoryHelp')" />
          </div>
          <details class="mt-3" @toggle="playerLog = readPlayerLog()">
            <summary class="cursor-pointer py-2 text-[15px]">{{ t('settings.playerLog') }}</summary>
            <p class="text-[13px] font-light text-muted">{{ t('settings.playerLogHelp') }}</p>
            <div class="mt-2 flex gap-2">
              <button type="button" class="pill" @click="copyLog">
                {{ logCopied ? t('settings.playerLogCopied') : t('settings.playerLogCopy') }}
              </button>
              <button type="button" class="pill" @click="clearLog">{{ t('settings.playerLogClear') }}</button>
            </div>
            <pre class="mt-2 max-h-80 overflow-auto whitespace-pre-wrap break-all rounded-xl bg-surface p-3 text-[11px] leading-snug">{{ playerLog || t('settings.playerLogEmpty') }}</pre>
          </details>
        </section>

        <section v-if="shown === 'sound'" class="flex flex-col gap-1">
          <h2 class="hidden text-[22px] font-bold md:block">{{ t('settings.sound') }}</h2>
          <p v-if="isIos" class="rounded-xl bg-accent-soft px-3.5 py-2.5 text-[13px]">{{ appConfig.transcode ? t('settings.soundIosServer') : t('settings.soundIos') }}</p>
          <div class="flex flex-col divide-y divide-line">
            <template v-if="appConfig.transcode">
              <SelectRow v-model="ui.playerPrefs.quality" :title="t('settings.quality')" :hint="t('settings.qualityHelp')" :options="qualities" />
              <SelectRow v-model="ui.playerPrefs.qualityCellular" :title="t('settings.qualityCellular')" :hint="t('settings.qualityCellularHelp')" :options="qualities" />
            </template>
            <SelectRow v-model="ui.playerPrefs.leveling" :title="t('settings.leveling')" :hint="t('settings.levelingHelp')" :options="levelings" />
            <SelectRow v-model="ui.playerPrefs.crossfade" :title="t('settings.crossfade')" :hint="t('settings.crossfadeHelp')" :options="fades" />
            <ToggleRow v-model="ui.playerPrefs.eq" :title="t('settings.eq')" :hint="t('settings.eqHelp')" />
          </div>
          <EqualizerEditor class="mt-1" />
        </section>

        <section v-if="shown === 'autoplay'" class="flex flex-col gap-1">
          <h2 class="hidden text-[22px] font-bold md:block">{{ t('settings.autoplay') }}</h2>
          <div class="flex flex-col divide-y divide-line">
            <ToggleRow v-model="ui.playerPrefs.autoplay" :title="t('settings.autoplayOn')" :hint="t('settings.autoplayHelp')" />
            <SelectRow v-model="ui.playerPrefs.albumEnd" :title="t('settings.albumEnd')" :hint="t(ui.playerPrefs.autoplay ? 'settings.albumEndHelp' : 'settings.albumEndOff')" :options="albumEnds" :disabled="!ui.playerPrefs.autoplay" />
          </div>
        </section>

        <section v-if="shown === 'storage'" class="flex flex-col gap-1">
          <h2 class="hidden text-[22px] font-bold md:block">{{ t('settings.storage') }}</h2>
          <div class="flex flex-col divide-y divide-line">
            <SelectRow v-model="ui.playerPrefs.prefetchWifi" :title="t('settings.prefetchWifi')" :hint="t('settings.prefetchWifiHelp')" :options="counts" />
            <SelectRow v-model="ui.playerPrefs.prefetchCellular" :title="t('settings.prefetchCellular')" :hint="t('settings.prefetchCellularHelp')" :options="counts" />
            <SelectRow v-model="ui.playerPrefs.cacheMB" :title="t('settings.cacheSize')" :hint="t('settings.cacheSizeHelp')" :options="sizes" />
          </div>
          <div class="mt-2 flex items-center gap-4">
            <span class="flex-1 text-[14px] font-light text-muted">{{ t('settings.cacheUsed', { mb: mb(used) }) }}</span>
            <button type="button" class="pill" @click="clearCache">{{ t('settings.clearCache') }}</button>
          </div>
          <RouterLink v-if="canSave()" to="/downloads" class="mt-2 flex items-center gap-4">
            <span class="flex flex-1 flex-col">
              <span class="text-[15px]">{{ t('offline.title') }}</span>
              <span class="text-[13px] font-light text-muted">{{ t('settings.downloadsHelp', { mb: mb(savedBytes()) }) }}</span>
            </span>
            <span class="text-subtle">›</span>
          </RouterLink>
        </section>

        <section v-if="shown === 'audiobooks' && appConfig.audiobooks" class="flex flex-col gap-3">
          <h2 class="hidden text-[22px] font-bold md:block">{{ t('settings.audiobooks') }}</h2>
          <div class="flex flex-wrap gap-4">
            <label class="flex items-center gap-2.5 text-[15px]">
              {{ t('settings.skipBack') }}
              <select v-model.number="player.skipBack" class="pill-select">
                <option v-for="s in SKIPS" :key="s" :value="s">{{ t('settings.seconds', { n: s }) }}</option>
              </select>
            </label>
            <label class="flex items-center gap-2.5 text-[15px]">
              {{ t('settings.skipForward') }}
              <select v-model.number="player.skipForward" class="pill-select">
                <option v-for="s in SKIPS" :key="s" :value="s">{{ t('settings.seconds', { n: s }) }}</option>
              </select>
            </label>
          </div>
          <p class="text-[13px] font-light text-muted">{{ t('settings.audiobooksHelp') }}</p>
        </section>

        <section v-if="shown === 'install'" class="flex flex-col gap-3">
          <h2 class="hidden text-[22px] font-bold md:block">{{ t('settings.installTitle') }}</h2>
          <p v-if="native" class="font-light text-muted">{{ t('settings.inWindowsApp', { v: native.version }) }}</p>
          <p v-else-if="isStandalone" class="font-light text-muted">{{ t('settings.installed') }}</p>
          <button v-else-if="installPrompt" type="button" class="h-11 self-start rounded-full bg-ink px-5 text-[15px] text-on-ink" @click="install">{{ t('settings.installApp') }}</button>
          <p v-else-if="isIos" class="font-light text-muted">{{ t('settings.installIos') }}</p>
          <p v-else class="font-light text-muted">{{ t('settings.installOther') }}</p>

          <!-- a PC: the Windows app (tray, global shortcuts, keeps playing with the window closed) -->
          <div v-if="isWindows && !native" class="mt-4 flex flex-col gap-2.5 rounded-2xl bg-surface p-4">
            <h3 class="font-medium">{{ t('settings.windowsApp') }}</h3>
            <p class="text-[14px] font-light text-muted">{{ t('settings.windowsAppHelp') }}</p>
            <a
              :href="winApp?.url || winApp?.page || '#'"
              class="flex h-11 items-center gap-2 self-start rounded-full bg-ink px-5 text-[15px] text-on-ink"
              :class="winApp ? '' : 'pointer-events-none opacity-50'"
              :download="winApp?.url ? '' : undefined"
              rel="noopener"
            >
              <Download :size="18" />{{ winApp?.version ? t('settings.windowsDownloadV', { v: winApp.version }) : t('settings.windowsDownload') }}
            </a>
            <p v-if="winApp?.size" class="text-[13px] font-light text-muted">{{ mb(winApp.size) }} MB · {{ t('settings.windowsUnsigned') }}</p>
            <a v-if="winApp && winApp.url" :href="winApp.page" target="_blank" rel="noopener" class="self-start text-[13px] text-muted underline">{{ t('settings.windowsReleases') }}</a>
          </div>
          <div v-if="winUpdate" class="mt-2 flex flex-col items-start gap-2.5 rounded-2xl bg-surface p-4">
            <p class="text-[14px]">{{ t('settings.windowsNewer', { v: winApp!.version }) }}</p>
            <template v-if="native?.update && winApp!.url">
              <button type="button" class="flex h-11 items-center gap-2 rounded-full bg-ink px-5 text-[15px] text-on-ink disabled:opacity-60" :disabled="updating !== null" @click="updateApp">
                <Download :size="18" />{{ updating === null ? t('settings.windowsUpdate') : updating >= 1 ? t('settings.windowsInstalling') : t('settings.windowsUpdating', { n: Math.round(updating * 100) }) }}
              </button>
              <span v-if="updating !== null" class="h-1 w-full max-w-xs rounded-full bg-line"><span class="block h-full rounded-full bg-accent transition-[width]" :style="{ width: `${Math.round(updating * 100)}%` }" /></span>
              <p class="text-[13px] font-light text-muted">{{ t('settings.windowsUpdateHelp') }}</p>
            </template>
            <a v-else :href="winApp!.url || winApp!.page" class="text-[14px] text-accent underline">{{ t('settings.windowsDownload') }}</a>
            <p v-if="updateError" class="text-[13px] text-danger">{{ updateError }}</p>
          </div>

          <!-- a phone: which icon the home screen gets -->
          <div v-if="phone && !native" class="mt-4 flex flex-col gap-2.5">
            <h3 class="font-medium">{{ t('settings.appIcon') }}</h3>
            <div class="flex flex-wrap gap-2.5" role="radiogroup" :aria-label="t('settings.appIcon')">
              <button
                v-for="v in APP_ICONS"
                :key="v"
                type="button"
                role="radio"
                :aria-checked="ui.appIcon === v"
                class="flex w-[56px] flex-col items-center gap-1.5 text-[12px]"
                :class="ui.appIcon === v ? 'font-medium' : 'text-muted'"
                @click="ui.appIcon = v"
              >
                <span class="relative block size-[52px] overflow-hidden rounded-[13px] ring-offset-2 ring-offset-bg" :class="ui.appIcon === v ? 'ring-2 ring-ink' : 'ring-1 ring-line'">
                  <!-- auto: half light, half dark -->
                  <img :src="iconFile(v)" alt="" class="size-full" />
                  <img v-if="v === 'auto'" src="/icon-dark-180.png" alt="" class="absolute inset-0 size-full [clip-path:polygon(100%_0,100%_100%,0_100%)]" />
                  <span v-if="ui.appIcon === v" class="absolute bottom-1 right-1 grid size-4 place-items-center rounded-full bg-ink text-on-ink"><Check :size="11" :stroke-width="3" /></span>
                </span>
                {{ t(`settings.appIcon_${v}`) }}
              </button>
            </div>
            <p class="text-[13px] font-light leading-relaxed text-muted">{{ isIos ? t('settings.appIconIos') : t('settings.appIconAndroid') }}</p>
          </div>
        </section>

        <section v-if="shown === 'about'" class="flex flex-col gap-5">
          <h2 class="hidden text-[22px] font-bold md:block">{{ t('settings.about') }}</h2>
          <div class="flex items-center gap-4">
            <AppLogo :size="48" :wordmark="false" />
            <div class="flex flex-col">
              <span class="text-[20px] font-bold">muzplayer</span>
              <span class="font-display text-[14px] text-muted">{{ version ? t('settings.version', { v: version }) : '' }}</span>
              <span v-if="native" class="text-[13px] text-muted">{{ t('settings.inWindowsApp', { v: native.version }) }}</span>
            </div>
          </div>
          <p class="text-[14px] font-light leading-relaxed text-soft">{{ t('settings.aboutText') }}</p>
          <div class="flex flex-col gap-1 rounded-2xl bg-surface px-4 py-3.5 text-[14px]">
            <span class="text-[13px] text-muted">{{ t('settings.aboutLicenseTitle') }}</span>
            <span>GNU General Public License v3.0 or later (GPL-3.0-or-later)</span>
            <span class="text-[13px] font-light text-muted">{{ t('settings.aboutLicenseText') }}</span>
          </div>
          <ul class="flex flex-col divide-y divide-line">
            <li v-for="l in aboutLinks" :key="l.href">
              <a :href="l.href" target="_blank" rel="noopener" class="flex min-h-[52px] items-center gap-3 py-2 hover:text-accent">
                <span class="flex min-w-0 flex-1 flex-col">
                  <span class="text-[15px]">{{ t(l.label) }}</span>
                  <span class="truncate text-[12px] font-light text-muted">{{ l.href.replace('https://', '') }}</span>
                </span>
                <ExternalLink :size="16" :stroke-width="1.6" class="flex-none text-muted" />
              </a>
            </li>
          </ul>
        </section>

        <section v-if="shown === 'account'" class="flex flex-col gap-3">
          <h2 class="hidden text-[22px] font-bold md:block">{{ t('settings.account') }}</h2>
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
      </div>
    </div>
  </div>
</template>
