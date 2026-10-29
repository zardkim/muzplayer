import { i18n } from './i18n'

export function duration(seconds: number | null | undefined): string {
  if (seconds == null || !isFinite(seconds)) return '–:––'
  const s = Math.max(0, Math.floor(seconds))
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = String(s % 60).padStart(2, '0')
  return h ? `${h}:${String(m).padStart(2, '0')}:${sec}` : `${m}:${sec}`
}

export function dateTime(value: string | null | undefined): string {
  if (!value) return ''
  return new Intl.DateTimeFormat(i18n.global.locale.value, { dateStyle: 'medium', timeStyle: 'short' }).format(
    new Date(value),
  )
}

/** "3시간 12분" / "3h 12m": for book lengths and time left. */
export function longDuration(seconds: number | null | undefined): string {
  const t = i18n.global.t
  const total = Math.max(0, Math.round((seconds ?? 0) / 60))
  const h = Math.floor(total / 60)
  const m = total % 60
  if (h && m) return t('books.hoursMinutes', { h, m })
  if (h) return t('books.hours', { h })
  return t('books.minutes', { m: Math.max(m, seconds && seconds > 0 ? 1 : 0) })
}
