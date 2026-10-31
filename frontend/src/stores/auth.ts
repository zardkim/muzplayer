import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import { api, ApiError } from '../api'
import { clearAudioCache } from '../audioCache'
import { clearSaved } from '../offline'
import type { Account, User } from '../types'

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

  // add: another account on this device, the one signed in now stays (user switching)
  async function login(username: string, password: string, add = false) {
    user.value = await api<User>('/auth/login', { method: 'POST', body: { username, password, add } })
  }

  // the other accounts signed in on this device; switching to one starts the app afresh as it
  const accounts = ref<Account[]>([])
  async function loadAccounts() {
    accounts.value = await api<Account[]>('/auth/accounts').catch(() => [])
  }
  async function switchTo(userId: number, password?: string) {
    await api('/auth/switch', { method: 'POST', body: { user_id: userId, password } })
    window.location.assign('/')
  }

  // a fresh install: the first account is the admin
  async function setup(username: string, password: string) {
    user.value = await api<User>('/auth/setup', { method: 'POST', body: { username, password } })
  }

  /** Signs this account out. When another account on this device takes over, the app restarts as
   *  it; after the last one, what this device kept goes too. */
  async function logout() {
    const r = await api<{ user: User | null }>('/auth/logout', { method: 'POST' }).catch(() => ({ user: null }))
    if (r.user) {
      window.location.assign('/')
      return
    }
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

  return { user, checked, fetchMe, login, setup, logout, updateSettings, accounts, loadAccounts, switchTo }
})
