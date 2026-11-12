import { onBeforeUnmount, ref, watch, type Ref } from 'vue'
import { api } from './api'
import type { RadioStation } from './types'

// The station list (backend radio.py), asked for once: the Radio page and the radio player share it.
export interface StationList {
  regions: string[]
  stations: RadioStation[]
}
let list: Promise<StationList> | null = null

export function loadStations(): Promise<StationList> {
  list ??= api<StationList>('/radio/stations').catch((e) => {
    list = null // try again next time
    throw e
  })
  return list
}

/** After a station was added or deleted: the list is asked for again next time. */
export function forgetStations() {
  list = null
}

/** The stations of the region a station is listed under: the one picked on the Radio page if it is there. */
export function regionOf(st: RadioStation, picked: string | undefined): string {
  return picked && st.regions.includes(picked) ? picked : st.regions[0]
}

/** What a station has on air now (backend radio_now.py): title and hours, when its broadcaster says. */
export interface OnAir {
  title: string | null
  start: string | null // "HH:MM"
  end: string | null
}
const onAirKept = new Map<string, { at: number; value: Promise<OnAir | null> }>()
const ON_AIR_MS = 120_000

function fetchOnAir(id: string): Promise<OnAir | null> {
  const hit = onAirKept.get(id)
  if (hit && Date.now() - hit.at < ON_AIR_MS) return hit.value
  const value = api<OnAir>(`/radio/stations/${encodeURIComponent(id)}/now`).then((r) => (r.title ? r : null), () => null)
  onAirKept.set(id, { at: Date.now(), value })
  return value
}

/** The programme on air for the station given (null: none known), asked again every two minutes. */
export function useOnAir(id: Ref<string | null | undefined>) {
  const onAir = ref<OnAir | null>(null)
  let timer = 0
  async function load() {
    const want = id.value
    onAir.value = want ? await fetchOnAir(want) : null
    if (want !== id.value) return // changed meanwhile: that one's own load answers
  }
  watch(id, () => {
    onAir.value = null
    void load()
  }, { immediate: true })
  timer = window.setInterval(() => void load(), ON_AIR_MS + 1000)
  onBeforeUnmount(() => window.clearInterval(timer))
  return onAir
}

/** "Title · 22:00–23:00" */
export function onAirText(o: OnAir | null): string {
  if (!o?.title) return ''
  const hours = o.start ? ` · ${o.start}${o.end ? `–${o.end}` : ''}` : ''
  return o.title + hours
}
