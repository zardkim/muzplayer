import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import { router } from './router'
import { i18n, initLocale } from './i18n'
import { appConfig } from './config'
import { registerServiceWorker } from './pwa'
import './style.css'

async function start() {
  // runtime settings come from the server (.env), not from build-time variables
  const config = await fetch('/api/v1/config')
    .then((r) => (r.ok ? r.json() : null))
    .catch(() => null)
  initLocale(config?.default_locale)
  appConfig.audiobooks = !!config?.audiobooks
  ;(window as unknown as { __MUZ_VERSION__?: string }).__MUZ_VERSION__ = config?.version

  createApp(App).use(createPinia()).use(i18n).use(router).mount('#app')
  registerServiceWorker()
}

start()
