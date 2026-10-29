import { createI18n } from 'vue-i18n'
import ko from './locales/ko.json'
import en from './locales/en.json'

export const LOCALES = [
  { code: 'ko', label: '한국어' },
  { code: 'en', label: 'English' },
] as const
export type Locale = (typeof LOCALES)[number]['code']

const STORAGE_KEY = 'muz.locale'

export const i18n = createI18n({
  legacy: false,
  locale: 'ko',
  fallbackLocale: 'ko',
  messages: { ko, en },
})

function isLocale(v: unknown): v is Locale {
  return LOCALES.some((l) => l.code === v)
}

/** Browser choice wins, then the server's DEFAULT_LOCALE (.env), then Korean. */
export function initLocale(serverDefault?: string) {
  let saved: string | null = null
  try {
    saved = localStorage.getItem(STORAGE_KEY)
  } catch {
    /* storage unavailable */
  }
  applyLocale(isLocale(saved) ? saved : isLocale(serverDefault) ? serverDefault : 'ko')
}

function applyLocale(locale: Locale) {
  i18n.global.locale.value = locale
  document.documentElement.lang = locale
}

export function setLocale(locale: Locale) {
  applyLocale(locale)
  try {
    localStorage.setItem(STORAGE_KEY, locale)
  } catch {
    /* storage unavailable */
  }
}

export function errorMessage(e: unknown): string {
  const code = (e as { code?: string })?.code ?? 'unknown'
  const key = `errors.${code}`
  return i18n.global.te(key) ? i18n.global.t(key) : i18n.global.t('errors.unknown')
}
