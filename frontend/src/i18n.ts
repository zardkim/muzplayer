import { createI18n } from 'vue-i18n'
import ko from './locales/ko.json'

export const LOCALES = [
  { code: 'ko', label: '한국어' },
  { code: 'en', label: 'English' },
] as const
export type Locale = (typeof LOCALES)[number]['code']

const STORAGE_KEY = 'muz.locale'

// Korean is built in (it is also the fallback); another language is fetched when it is first used
export const i18n = createI18n({
  legacy: false,
  locale: 'ko',
  fallbackLocale: 'ko',
  messages: { ko } as Record<Locale, typeof ko>,
})
const loaders: Partial<Record<Locale, () => Promise<{ default: typeof ko }>>> = {
  en: () => import('./locales/en.json'),
}

function isLocale(v: unknown): v is Locale {
  return LOCALES.some((l) => l.code === v)
}

/** Browser choice wins, then the server's DEFAULT_LOCALE (.env), then Korean. */
export async function initLocale(serverDefault?: string) {
  let saved: string | null = null
  try {
    saved = localStorage.getItem(STORAGE_KEY)
  } catch {
    /* storage unavailable */
  }
  await applyLocale(isLocale(saved) ? saved : isLocale(serverDefault) ? serverDefault : 'ko')
}

async function applyLocale(locale: Locale) {
  const load = loaders[locale]
  if (load && !i18n.global.availableLocales.includes(locale)) {
    try {
      i18n.global.setLocaleMessage(locale, (await load()).default)
    } catch {
      return // offline before it was ever loaded: stay in the language shown
    }
  }
  i18n.global.locale.value = locale
  document.documentElement.lang = locale
}

export async function setLocale(locale: Locale) {
  await applyLocale(locale)
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
