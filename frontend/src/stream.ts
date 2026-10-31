import { query } from './api'
import { appConfig } from './config'
import { isIos } from './pwa'
import { useUi } from './stores/ui'
import type { Track } from './types'

// The address a song is played from. With ffmpeg on the server (appConfig.transcode) it can ask
// for a converted copy (backend transcode.py): a lower bitrate per Settings, MP3 for formats this
// browser can't play, and on iPhone the volume levelling, which the page can't do there without
// risking silence on a locked screen.

export type Quality = 'orig' | '320' | '256' | '192' | '128'
export const QUALITIES: Quality[] = ['orig', '320', '256', '192', '128']

/** On mobile data (Android tells us; iPhone doesn't, so it counts as Wi-Fi). */
export function onCellular(): boolean {
  const c = (navigator as Navigator & { connection?: { type?: string } }).connection
  return c?.type === 'cellular'
}

const plays = new Map<string, boolean>()
function browserPlays(format: string): boolean {
  if (format === 'wma' || format === 'ape') return false
  if (format !== 'aif' && format !== 'aiff') return true
  if (!plays.has(format)) plays.set(format, new Audio().canPlayType('audio/aiff') !== '') // Safari only
  return plays.get(format)!
}

/** Levelling is done by the server: on iPhone, when it can convert. */
export function serverLevels(): boolean {
  return isIos && appConfig.transcode && useUi().playerPrefs.leveling !== 'off'
}

export const streamBase = (trackId: number) => `/api/v1/tracks/${trackId}/stream`

export function trackSrc(track: Track): string {
  const base = streamBase(track.id)
  if (!appConfig.transcode) return base
  const prefs = useUi().playerPrefs
  let quality = onCellular() ? prefs.qualityCellular : prefs.quality
  if (quality === 'orig' && !browserPlays(track.format)) quality = '320'
  const level = serverLevels() ? prefs.leveling : 'off'
  return base + query({ quality: quality === 'orig' ? null : quality, level: level === 'off' ? null : level })
}

/** A URL the server may answer with a conversion still being written (no length, no seeking). */
export const mayConvert = (src: string) => src.includes('/stream?')
