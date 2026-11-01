import { watch } from 'vue'
import { usePlayer } from './stores/player'

// The Windows app (muzplayer-windows, Electron) shows this web app in its window and adds a tray
// and global shortcuts. When it does, its preload puts window.muzNative here: we tell it what
// plays (the tray's tooltip and menu, the taskbar's progress) and run its commands. In a browser
// there is no window.muzNative and none of this runs.

type Command = 'toggle' | 'next' | 'prev'
interface MuzNative {
  platform: string
  version: string
  state(s: { title: string; artist: string; playing: boolean; position: number; duration: number }): void
  onCommand(handler: (cmd: Command) => void): void
}

export const native = (window as unknown as { muzNative?: MuzNative }).muzNative ?? null

export function connectNative() {
  if (!native) return
  const player = usePlayer()
  native.onCommand((cmd) => {
    if (cmd === 'toggle') player.toggle()
    else if (cmd === 'next') player.next()
    else if (cmd === 'prev') player.prev()
  })
  let lastSent = 0
  const send = () => {
    lastSent = Date.now()
    const live = player.mode === 'live' ? player.station : null
    const book = player.mode === 'book' ? player.book : null
    const track = player.mode === 'music' ? player.current : null
    native.state({
      title: live?.name ?? player.chapter?.title ?? book?.title ?? track?.title ?? '',
      artist: live ? 'LIVE' : book ? book.authors ?? '' : track?.artist ?? '',
      playing: player.playing,
      position: book ? player.bookPos : player.currentTime,
      duration: live ? 0 : book ? book.duration ?? 0 : player.duration,
    })
  }
  // on every change of song or play state, and every few seconds for the taskbar's progress
  watch(() => [player.mode, player.current?.id, player.station?.id, player.book?.id, player.chapter?.title, player.playing], send, { immediate: true })
  watch(() => player.currentTime, () => {
    if (Date.now() - lastSent > 5000) send()
  })
}
