import type { RadioStation } from './types'

// The Radio page's tuner: the stations of a region laid on a dial by their frequency (radio_stations.json
// "freq", by region). FM 88.0–108.0 MHz in 0.1 steps, AM 531–1602 kHz in 9 kHz steps; NET: the stations
// with no frequency (internet only, one's own), one channel each. A place on the dial is a step number.

export type Band = 'FM' | 'AM' | 'NET'
export const BANDS: Band[] = ['FM', 'AM', 'NET']

interface Scale {
  min: number // the first step's value (FM in 0.1 MHz, AM in kHz)
  step: number
  steps: number // how many
  px: number // width of a step on the dial
  mid: number // a longer tick every this many steps
  major: number // a labelled tick every this many steps
}
const SCALES: Record<'FM' | 'AM', Scale> = {
  FM: { min: 880, step: 1, steps: 201, px: 10, mid: 5, major: 10 },
  AM: { min: 531, step: 9, steps: 120, px: 12, mid: 5, major: 10 },
}
export const NET_PX = 56

/** One place on the dial with its station(s): two stations of a region may share a frequency. */
export interface DialStop {
  step: number
  stations: RadioStation[]
}

export interface Dial {
  band: Band
  steps: number
  px: number
  mid: number
  major: number
  stops: DialStop[] // by step
  label: (step: number) => string // "89.1", "711", "03"
}

/** A station's place in a region: its band and value ("FM 89.1" -> FM, 891), or null (NET). */
export function placeOf(st: RadioStation, region: string): { band: 'FM' | 'AM'; value: number } | null {
  const m = /^(FM|AM)\s+(\d+(?:\.\d)?)$/.exec(st.freq?.[region] ?? '')
  if (!m) return null
  const band = m[1] as 'FM' | 'AM'
  return { band, value: band === 'FM' ? Math.round(Number(m[2]) * 10) : Number(m[2]) }
}

export function bandOf(st: RadioStation, region: string): Band {
  return placeOf(st, region)?.band ?? 'NET'
}

export function dialFor(stations: RadioStation[], region: string, band: Band): Dial {
  if (band === 'NET') {
    const net = stations.filter((s) => !placeOf(s, region))
    return {
      band, steps: Math.max(1, net.length), px: NET_PX, mid: 1, major: 1,
      stops: net.map((s, i) => ({ step: i, stations: [s] })),
      label: (i) => String(i + 1).padStart(2, '0'),
    }
  }
  const sc = SCALES[band]
  const at = new Map<number, RadioStation[]>()
  for (const s of stations) {
    const p = placeOf(s, region)
    if (p?.band !== band) continue
    const step = Math.round((p.value - sc.min) / sc.step)
    if (step < 0 || step >= sc.steps) continue
    at.set(step, [...(at.get(step) ?? []), s])
  }
  return {
    band, steps: sc.steps, px: sc.px, mid: sc.mid, major: sc.major,
    stops: [...at.entries()].sort((a, b) => a[0] - b[0]).map(([step, list]) => ({ step, stations: list })),
    label: (i) => (band === 'FM' ? ((sc.min + i * sc.step) / 10).toFixed(1) : String(sc.min + i * sc.step)),
  }
}

/** The dial's labelled ticks read better as round numbers: FM's whole MHz ("90"), AM's every 90 kHz. */
export function tickLabel(dial: Dial, step: number): string {
  return dial.band === 'FM' ? String(Math.round(Number(dial.label(step)))) : dial.label(step)
}

/** The station's step on this dial, or null when it isn't on it. */
export function stepOf(dial: Dial, id: string): number | null {
  return dial.stops.find((s) => s.stations.some((x) => x.id === id))?.step ?? null
}

/** The stop after (1) or before (-1) a step, round the end of the dial. */
export function nextStop(dial: Dial, from: number, dir: 1 | -1): DialStop | null {
  if (!dial.stops.length) return null
  const list = dir === 1 ? dial.stops : [...dial.stops].reverse()
  return list.find((s) => (dir === 1 ? s.step > from : s.step < from)) ?? list[0]
}
