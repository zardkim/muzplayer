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
