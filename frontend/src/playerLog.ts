// What the player saw lately (pauses, calls, output changes, lock screen buttons, play() refusals),
// kept on the device for Settings → Player → playback log: an iPhone's calls and lock screen can't
// be tried anywhere else, so a real one leaves this trace to read afterwards.
const KEY = 'muz.playerLog'
const KEPT = 300

let lines: string[] | null = null
let saveTimer = 0

function load(): string[] {
  if (lines) return lines
  try {
    lines = JSON.parse(localStorage.getItem(KEY) || '[]')
  } catch {
    lines = []
  }
  return lines!
}

function stamp() {
  const d = new Date()
  const p = (n: number, w = 2) => String(n).padStart(w, '0')
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}.${p(d.getMilliseconds(), 3)}`
}

export function plog(event: string, detail = '') {
  const all = load()
  all.push(`${stamp()} ${event}${detail ? ' ' + detail : ''}`)
  if (all.length > KEPT) all.splice(0, all.length - KEPT)
  // written a moment later (timeupdate-free, but several come at once); at once when the page hides
  window.clearTimeout(saveTimer)
  saveTimer = window.setTimeout(save, 500)
}

function save() {
  try {
    localStorage.setItem(KEY, JSON.stringify(load()))
  } catch {
    /* not kept */
  }
}
window.addEventListener('pagehide', save)
document.addEventListener('visibilitychange', () => document.hidden && save())

export function readPlayerLog(): string {
  return load().join('\n')
}

export function clearPlayerLog() {
  lines = []
  save()
}
