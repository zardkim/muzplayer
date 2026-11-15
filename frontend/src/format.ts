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

/** "5분 전" / "5 minutes ago": how long ago, in the largest whole unit. */
export function ago(value: string | null | undefined): string {
  if (!value) return ''
  const s = Math.max(0, (Date.now() - new Date(value).getTime()) / 1000)
  const rtf = new Intl.RelativeTimeFormat(i18n.global.locale.value, { numeric: 'auto' })
  for (const [unit, size] of [['day', 86400], ['hour', 3600], ['minute', 60]] as const) {
    if (s >= size) return rtf.format(-Math.floor(s / size), unit)
  }
  return rtf.format(0, 'second')
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

/** "FLAC 24/96" for lossless songs, "MP3 320k" for the rest; just the format when unknown. */
export function codec(track: { format: string; sample_rate?: number; bit_depth?: number; bitrate?: number }): string {
  const name = track.format.toUpperCase()
  if (track.bit_depth && track.sample_rate) {
    const khz = track.sample_rate / 1000
    return `${name} ${track.bit_depth}/${Number.isInteger(khz) ? khz : khz.toFixed(1)}`
  }
  return track.bitrate ? `${name} ${track.bitrate}k` : name
}

/** A chart source's name to put before "차트"/"chart" in a label: "멜론 차트" -> "멜론", so "{source} 차트"
 * doesn't say it twice ('' for a source named just "차트"). */
/** The chart site's logo (public/logos), for a source folder named after it. */
const SOURCE_LOGOS: [RegExp, string][] = [
  [/멜론|melon/i, 'melon.png'],
  [/벅스|bugs/i, 'bugs.png'],
  [/지니|genie/i, 'genie.png'],
  [/올레|olleh/i, 'olleh.svg'],
  [/빌보드|billboard/i, 'billboard.png'],
]
export function sourceLogo(source: string): string | null {
  const hit = SOURCE_LOGOS.find(([rx]) => rx.test(source))
  return hit ? `/logos/${hit[1]}` : null
}

export function chartSource(source: string): string {
  return source.replace(/\s*(?:차트|charts?)\s*$/i, '').trim()
}

/** Added in the last week (the NEW badge on albums, charts and themes; the news page's default span too). */
export const NEW_DAYS = 7
export function isNew(created: string | null | undefined): boolean {
  return !!created && Date.now() - new Date(created).getTime() < NEW_DAYS * 86_400_000
}
