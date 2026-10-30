import { goBack, router } from './router'
import { usePlayer } from './stores/player'
import { useUi } from './stores/ui'

// Opening the player: on a PC the songs player is a page of its own (/playing, inside the sidebar
// and bars); on a phone, and for audiobooks, it is the full-screen sheet.
export function openPlayer(tab?: 'lyrics' | 'queue') {
  const ui = useUi()
  if (tab) ui.playerTab = tab
  if (ui.wide && usePlayer().mode === 'music') {
    if (router.currentRoute.value.name !== 'playing') router.push({ name: 'playing' })
  } else ui.playerOpen = true
}

// the bar's artwork toggles the PC player page
export function togglePlayer() {
  if (router.currentRoute.value.name === 'playing') goBack()
  else openPlayer()
}
