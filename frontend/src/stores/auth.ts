import { defineStore } from 'pinia'
import { ref } from 'vue'
import { api } from '../api'
import { clearAudioCache } from '../audioCache'
import type { User } from '../types'

export const useAuth = defineStore('auth', () => {
  const user = ref<User | null>(null)
  const checked = ref(false)

  async function fetchMe() {
    try {
      user.value = await api<User>('/auth/me')
    } catch {
      user.value = null
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
  }

  // this person's own settings, kept on the server (the same on every device)
  async function updateSettings(body: { record_history?: boolean; home_sections?: { key: string; on: boolean }[] }) {
    user.value = await api<User>('/auth/me', { method: 'PATCH', body })
  }

  return { user, checked, fetchMe, login, setup, logout, updateSettings }
})
