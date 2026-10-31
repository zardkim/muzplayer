import { reactive } from 'vue'
import { api } from './api'
import { isIos } from './pwa'
import type { Track } from './types'

// Chromecast through Google's Cast web sender and its default media receiver (Chrome on a PC or
// Android, over https). The Cast device fetches the songs itself with signed links from the server
// (backend api/cast.py), so it plays on without this page; the devices sheet controls it.
// The SDK is loaded only when the devices sheet first opens.

/* eslint-disable @typescript-eslint/no-explicit-any */
declare const cast: any
declare const chrome: any

const SDK = 'https://www.gstatic.com/cv/js/sender/v1/cast_sender.js?loadCastFramework=1'
const QUEUE = 100 // songs sent from the current one on

export const castState = reactive({
  ready: false, // the SDK is in
  devices: false, // a Cast device is on the network
  active: false, // casting now
  name: '',
  playing: false,
  position: 0,
  duration: 0,
  volume: 1,
  title: '',
  artist: '',
  image: '',
})

let loading = false
let player: any = null
let controller: any = null

export const castSupported = () => !isIos && window.isSecureContext && /Chrome\//.test(navigator.userAgent)

export function loadCast() {
  if (loading || !castSupported()) return
  loading = true
  ;(window as any).__onGCastApiAvailable = (ok: boolean) => ok && init()
  const s = document.createElement('script')
  s.src = SDK
  s.async = true
  document.head.appendChild(s)
}

const context = () => cast.framework.CastContext.getInstance()

function init() {
  const ctx = context()
  ctx.setOptions({ receiverApplicationId: chrome.cast.media.DEFAULT_MEDIA_RECEIVER_APP_ID, autoJoinPolicy: chrome.cast.AutoJoinPolicy.ORIGIN_SCOPED })
  ctx.addEventListener(cast.framework.CastContextEventType.CAST_STATE_CHANGED, (e: any) => {
    castState.devices = e.castState !== cast.framework.CastState.NO_DEVICES_AVAILABLE
  })
  player = new cast.framework.RemotePlayer()
  controller = new cast.framework.RemotePlayerController(player)
  controller.addEventListener(cast.framework.RemotePlayerEventType.ANY_CHANGE, sync)
  castState.devices = ctx.getCastState() !== cast.framework.CastState.NO_DEVICES_AVAILABLE
  castState.ready = true
  sync()
}

function sync() {
  const md = player.mediaInfo?.metadata
  Object.assign(castState, {
    active: !!player.isConnected,
    name: context().getCurrentSession()?.getCastDevice()?.friendlyName ?? '',
    playing: !!player.isMediaLoaded && !player.isPaused,
    position: player.currentTime || 0,
    duration: player.duration || 0,
    volume: player.volumeLevel ?? 1,
    title: md?.title ?? '',
    artist: md?.artist ?? '',
    image: md?.images?.[0]?.url ?? '',
  })
}

/** Picks a Cast device (Chrome's list) unless one is connected, and plays the queue there from
 *  this song and position. Throws when the person cancels or the device refuses. */
export async function castQueue(queue: Track[], index: number, position: number) {
  const ctx = context()
  if (!ctx.getCurrentSession()) await ctx.requestSession()
  const session = ctx.getCurrentSession()
  const tracks = queue.slice(index, index + QUEUE)
  const links = await api<Record<string, { src: string; type: string; cover: string | null }>>('/cast/links', {
    method: 'POST',
    body: { track_ids: tracks.map((t) => t.id) },
  })
  const items = tracks
    .filter((t) => links[t.id])
    .map((t, i) => {
      const link = links[t.id]
      const info = new chrome.cast.media.MediaInfo(location.origin + link.src, link.type)
      info.streamType = chrome.cast.media.StreamType.BUFFERED
      const md = new chrome.cast.media.MusicTrackMediaMetadata()
      md.title = t.title
      md.artist = t.artist
      md.albumName = t.album
      if (link.cover) md.images = [new chrome.cast.Image(location.origin + link.cover)]
      info.metadata = md
      const item = new chrome.cast.media.QueueItem(info)
      item.autoplay = true
      if (i === 0 && position > 1) item.startTime = position
      return item
    })
  if (!items.length) throw new Error('nothing')
  const request = new chrome.cast.media.QueueLoadRequest(items)
  await new Promise((resolve, reject) => session.getSessionObj().queueLoad(request, resolve, reject))
}

const media = () => context().getCurrentSession()?.getMediaSession()
const ignore = () => {}

export const castControl = {
  toggle: () => controller?.playOrPause(),
  next: () => media()?.queueNext(ignore, ignore),
  prev: () => media()?.queuePrev(ignore, ignore),
  seek(seconds: number) {
    player.currentTime = seconds
    controller.seek()
  },
  volume(level: number) {
    player.volumeLevel = level
    controller.setVolumeLevel()
  },
  stop: () => context().endCurrentSession(true),
}
