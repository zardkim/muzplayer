import { ref } from 'vue'
import { setGraphSink } from './audioGraph'
import { isIos } from './pwa'

// Where this device plays the sound: the phone's speaker, Bluetooth headphones, a USB DAC...
//
// - iPhone/iPad: Safari's own route picker (the AirPlay sheet) lists the speaker, Bluetooth and
//   AirPlay devices; the audio session is "playback" so it keeps playing in the background and
//   follows Bluetooth when it connects (player.ts).
// - Chrome/Edge on a PC: the outputs are listed here and the song is sent to the one picked
//   (setSinkId); Firefox asks with its own picker (selectAudioOutput).
// - Android: the system routes media to Bluetooth as soon as it connects; another output is picked
//   in the media notification (Chrome on Android can't choose one itself).

type Sinkable = HTMLMediaElement & { setSinkId?: (id: string) => Promise<void> }
type Devices = MediaDevices & { selectAudioOutput?: () => Promise<MediaDeviceInfo> }

export interface Output { id: string; label: string }
export const outputs = ref<Output[]>([])
export const sinkId = ref('') // '' = the system's default (it moves to Bluetooth by itself)

const isAndroid = /Android/.test(navigator.userAgent)
// (over plain http, e.g. the NAS opened by its IP, there is no navigator.mediaDevices at all)
const canSink = 'setSinkId' in HTMLMediaElement.prototype && !isAndroid && !!navigator.mediaDevices
// 'none': a PC browser that can't choose (or a plain-http page): the row is left out
export const outputKind: 'ios' | 'list' | 'picker' | 'system' | 'none' = isIos
  ? 'ios'
  : (navigator.mediaDevices as Devices | undefined)?.selectAudioOutput
    ? 'picker'
    : canSink
      ? 'list'
      : isAndroid
        ? 'system'
        : 'none'

let element: Sinkable | null = null

export function attachOutputs(audio: HTMLAudioElement) {
  element = audio
  navigator.mediaDevices?.addEventListener?.('devicechange', () => void refreshOutputs(true))
}

/** The outputs the browser shows (names appear once it has been allowed to list them). */
export async function refreshOutputs(changed = false) {
  if (outputKind !== 'list') return
  const all = await navigator.mediaDevices.enumerateDevices().catch(() => [] as MediaDeviceInfo[])
  outputs.value = all.filter((d) => d.kind === 'audiooutput' && d.deviceId && d.deviceId !== 'default' && d.deviceId !== 'communications')
    .map((d, i) => ({ id: d.deviceId, label: d.label || `#${i + 1}` }))
  // the picked one went away (headphones unplugged, Bluetooth off): back to the default
  if (changed && sinkId.value && !outputs.value.some((o) => o.id === sinkId.value)) await useOutput('')
}

export async function useOutput(id: string) {
  await element?.setSinkId?.(id)
  setGraphSink(id)
  sinkId.value = id
}

/** Firefox: its own picker. */
export async function pickOutput() {
  const d = await (navigator.mediaDevices as Devices).selectAudioOutput!()
  await useOutput(d.deviceId)
}
