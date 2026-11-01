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

/** The stations of the region a station is listed under: the one picked on the Radio page if it is there. */
export function regionOf(st: RadioStation, picked: string | undefined): string {
  return picked && st.regions.includes(picked) ? picked : st.regions[0]
}
