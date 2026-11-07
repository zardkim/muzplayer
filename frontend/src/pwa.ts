import { ref } from 'vue'

interface InstallPromptEvent extends Event {
  prompt: () => Promise<void>
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>
}

/** Android/desktop Chrome hands us an install prompt; iOS has none (Share → Add to Home Screen). */
export const installPrompt = ref<InstallPromptEvent | null>(null)
export const isStandalone =
  window.matchMedia('(display-mode: standalone)').matches || (navigator as { standalone?: boolean }).standalone === true
export const isAndroid = /Android/.test(navigator.userAgent)
export const isWindows = /Windows NT/.test(navigator.userAgent)
export const isIos = /iPad|iPhone|iPod/.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1)

window.addEventListener('beforeinstallprompt', (e) => {
  e.preventDefault()
  installPrompt.value = e as InstallPromptEvent
})
window.addEventListener('appinstalled', () => (installPrompt.value = null))

export async function install() {
  const p = installPrompt.value
  if (!p) return
  await p.prompt()
  await p.userChoice
  installPrompt.value = null
}

export function registerServiceWorker() {
  if (import.meta.env.PROD && 'serviceWorker' in navigator) {
    const register = () => navigator.serviceWorker.register('/sw.js').catch(() => {})
    // the app mounts after an async config fetch, so `load` may already have fired
    if (document.readyState === 'complete') register()
    else window.addEventListener('load', register)
  }
}
