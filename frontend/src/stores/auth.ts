import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import { api, ApiError } from '../api'
import { clearAudioCache } from '../audioCache'
import { clearSaved } from '../offline'
import type { User } from '../types'

// the signed-in user as last seen, so the app opens offline (saved songs, Library → downloads);
// only the server saying "not signed in" signs out
const ME_KEY = 'muz.me'
function remember(u: User | null) {
  try {
    if (u) localStorage.setItem(ME_KEY, JSON.stringify(u))
    else localStorage.removeItem(ME_KEY)
  } catch {
    /* storage unavailable */
  }
}
function remembered(): User | null {
  try {
    return JSON.parse(localStorage.getItem(ME_KEY) || 'null')
  } catch {
    return null
  }
}

export const useAuth = defineStore('auth', () => {
  const user = ref<User | null>(null)
  const checked = ref(false)
  watch(user, remember)

  async function fetchMe() {
    try {
      user.value = await api<User>('/auth/me')
    } catch (e) {
      user.value = e instanceof ApiError && e.status === 0 ? remembered() : null
    } finally {
      checked.value = true
    }
  }

  async function login(username: string, password: string) {
    user.value = await api<User>('/auth/login', { method: 'POST', body: { username, password } })
  }

  // a fresh install: the first account is the admin
  async function setup(username: string, password: string) {
    user.value = await api<User>('/auth/setup', { method: 'POST', body: { username, password } })
  }

  async function logout() {
    await api('/auth/logout', { method: 'POST' }).catch(() => {})
    user.value = null
    // covers kept by sw.js: the next person on this device shouldn't see what was browsed
    await globalThis.caches?.delete('muz-covers-v1').catch(() => {}) // no Cache API over plain http
    await clearAudioCache(true)
    await clearSaved()
  }

  // this person's own settings, kept on the server (the same on every device)
  async function updateSettings(body: { record_history?: boolean; home_sections?: { key: string; on: boolean }[] }) {
    user.value = await api<User>('/auth/me', { method: 'PATCH', body })
  }

  return { user, checked, fetchMe, login, setup, logout, updateSettings }
})
