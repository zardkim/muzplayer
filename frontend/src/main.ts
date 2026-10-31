import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { ApiError } from './api'
import { useUi } from './stores/ui'
import App from './App.vue'
import { router } from './router'
import { i18n, initLocale } from './i18n'
import { appConfig } from './config'
import { warmDownloadsPage } from './offline'
import { registerServiceWorker } from './pwa'
import './style.css'

const CONFIG_KEY = 'muz.config'

function showError(err: unknown) {
  // a failed request (offline, the server restarting, a 404) is the page's own business, not a broken page
  if (err instanceof ApiError || (err instanceof Error && ['AbortError', 'TypeError'].includes(err.name) && /fetch|abort|network/i.test(err.message))) return
  try {
    const text = err instanceof Error ? err.message : String(err)
    useUi().notify(i18n.global.t('errors.page', { text: text.slice(0, 160) }), true)
  } catch {
    /* before the stores are up */
  }
}

async function start() {
  // runtime settings come from the server, not from build-time variables
  // offline: the last one this device got, so saved songs still play as they did
  let config = await fetch('/api/v1/config')
    .then((r) => (r.ok ? r.json() : null))
    .catch(() => null)
  try {
    if (config) localStorage.setItem(CONFIG_KEY, JSON.stringify(config))
    else config = JSON.parse(localStorage.getItem(CONFIG_KEY) || 'null')
  } catch {
    /* storage unavailable */
  }
  initLocale(config?.default_locale)
  appConfig.audiobooks = !!config?.audiobooks
  appConfig.aiBanners = !!config?.ai_banners
  appConfig.youtubeSearch = !!config?.youtube_search
  appConfig.needsSetup = !!config?.needs_setup
  appConfig.transcode = !!config?.transcode
  appConfig.aiPlaylists = !!config?.ai_playlists
  ;(window as unknown as { __MUZ_VERSION__?: string }).__MUZ_VERSION__ = config?.version

  const app = createApp(App).use(createPinia()).use(i18n).use(router)
  // an error on a page says so instead of leaving it blank or silently half-drawn (and its text
  // helps tell what happened)
  app.config.errorHandler = (err, _instance, info) => {
    console.error(err, info)
    showError(err)
  }
  window.addEventListener('unhandledrejection', (e) => console.error('unhandled', e.reason))
  app.mount('#app')
  registerServiceWorker()
  warmDownloadsPage() // after an update its file name changes
}

start()
