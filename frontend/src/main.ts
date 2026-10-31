import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import { router } from './router'
import { i18n, initLocale } from './i18n'
import { appConfig } from './config'
import { warmDownloadsPage } from './offline'
import { registerServiceWorker } from './pwa'
import './style.css'

const CONFIG_KEY = 'muz.config'

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
  ;(window as unknown as { __MUZ_VERSION__?: string }).__MUZ_VERSION__ = config?.version

  createApp(App).use(createPinia()).use(i18n).use(router).mount('#app')
  registerServiceWorker()
  warmDownloadsPage() // after an update its file name changes
}

start()
