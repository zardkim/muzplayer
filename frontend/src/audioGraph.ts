// Sound processing for music: volume levelling (ReplayGain), a 10-band equaliser and crossfades.
//
// All three need Web Audio: the <audio> element is fed into an AudioContext, and from then on its
// sound only comes out through that context (there is no undoing it until the page reloads). So
// the graph is built only when one of them is first turned on, never for people who don't use them.
//
//   main <audio> ─ source ─ gain (levelling × fade in) ─┐
//   tail <audio> ─ source ─ gain (levelling × fade out) ┴─ 10 filters (EQ) ─ speakers
//
// The tail plays the end of the outgoing song during a crossfade, while the main element (which
// the rest of the player follows) has already moved on to the next one.
//
// iPhone: Safari may silence an AudioContext when the screen locks, so these stay off there unless
// the person turns them on knowingly (Settings says so).

export const EQ_BANDS = [31, 62, 125, 250, 500, 1000, 2000, 4000, 8000, 16000]
export const EQ_PRESETS: Record<string, number[]> = {
  flat: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
  bass: [6, 5, 4, 2, 0, 0, 0, 0, 0, 0],
  treble: [0, 0, 0, 0, 0, 1, 2, 4, 5, 6],
  vocal: [-2, -2, -1, 1, 3, 4, 3, 1, 0, -1],
  rock: [4, 3, 1, 0, -1, -1, 1, 2, 3, 4],
  pop: [-1, 0, 2, 3, 3, 1, 0, 0, 1, 1],
  jazz: [3, 2, 1, 2, -1, -1, 0, 1, 2, 3],
  classical: [3, 2, 1, 0, 0, 0, 0, 1, 2, 3],
  electronic: [5, 4, 1, 0, -2, 1, 0, 1, 4, 5],
  night: [-4, -3, -2, 0, 1, 1, 0, -1, -2, -3], // softer lows and highs for quiet listening
}

type Chain = { el: HTMLAudioElement; gain: GainNode }

let ctx: AudioContext | null = null
let main: Chain | null = null
let tail: Chain | null = null
let filters: BiquadFilterNode[] = []
let levelDb = 0 // the main song's levelling gain

const dbToGain = (db: number) => Math.pow(10, db / 20)

/** True once the main element plays through Web Audio. */
export const graphActive = () => ctx !== null

function build(el: HTMLAudioElement) {
  ctx = new AudioContext()
  filters = EQ_BANDS.map((f, i) => {
    const node = ctx!.createBiquadFilter()
    node.type = i === 0 ? 'lowshelf' : i === EQ_BANDS.length - 1 ? 'highshelf' : 'peaking'
    node.frequency.value = f
    node.Q.value = 1.1
    node.gain.value = 0
    return node
  })
  for (let i = 0; i < filters.length - 1; i++) filters[i].connect(filters[i + 1])
  filters[filters.length - 1].connect(ctx.destination)
  main = connect(el)
  // the tail never takes part in the player's state, media session or history
  const t = new Audio()
  t.preload = 'auto'
  tail = connect(t)
  tail.gain.gain.value = 0
}

function connect(el: HTMLAudioElement): Chain {
  const gain = ctx!.createGain()
  ctx!.createMediaElementSource(el).connect(gain)
  gain.connect(filters[0])
  return { el, gain }
}

/** Builds the graph around the main element the first time a sound feature is turned on.
 *  False when the browser refused (nothing is left half-built: the song plays on as before). */
export function ensureGraph(el: HTMLAudioElement): boolean {
  if (ctx) return true
  try {
    build(el)
    return true
  } catch (e) {
    console.error('sound processing unavailable', e)
    void (ctx as AudioContext | null)?.close().catch(() => {}) // build() may have stopped part-way
    ctx = main = tail = null
    filters = []
    return false
  }
}

/** Call from a tap (play, next...): browsers start an AudioContext only after a user gesture. */
export function resumeGraph() {
  if (ctx && ctx.state !== 'running') void ctx.resume().catch(() => {})
}

/** The levelling gain for the song that is starting on the main element. */
export function setLevel(db: number) {
  levelDb = db
  if (!main || !ctx) return
  main.gain.gain.cancelScheduledValues(ctx.currentTime)
  main.gain.gain.setValueAtTime(dbToGain(db), ctx.currentTime)
}

/** EQ band gains in dB (all zero = no change). */
export function setEq(gains: number[]) {
  if (!ctx) return
  filters.forEach((f, i) => f.gain.setTargetAtTime(gains[i] ?? 0, ctx!.currentTime, 0.05))
}

/** Loads the outgoing song into the tail a moment early, so the crossfade starts without a gap. */
export function primeTail(src: string, at: number) {
  if (!tail) return
  if (tail.el.src !== src) tail.el.src = src
  tail.el.currentTime = at
}

/** Crossfade: the tail plays on from `at` in the outgoing song and fades out over `seconds`,
 *  while the main element (already on the next song) fades in. */
export function crossfade(src: string, at: number, seconds: number, outgoingDb: number) {
  if (!ctx || !main || !tail) return
  const now = ctx.currentTime
  if (tail.el.src !== src) tail.el.src = src
  tail.el.currentTime = at
  void tail.el.play().catch(() => {})
  const t = tail.gain.gain
  t.cancelScheduledValues(now)
  t.setValueAtTime(dbToGain(outgoingDb), now)
  t.linearRampToValueAtTime(0, now + seconds)
  const m = main.gain.gain
  m.cancelScheduledValues(now)
  m.setValueAtTime(0.0001, now)
  m.linearRampToValueAtTime(dbToGain(levelDb), now + seconds)
  window.setTimeout(() => tail?.el.pause(), seconds * 1000 + 200)
}

/** Stops a crossfade in progress (pause, seek, another song picked). */
export function stopTail() {
  if (!tail || !ctx || !main) return
  tail.el.pause()
  tail.gain.gain.cancelScheduledValues(ctx.currentTime)
  tail.gain.gain.setValueAtTime(0, ctx.currentTime)
  main.gain.gain.cancelScheduledValues(ctx.currentTime)
  main.gain.gain.setValueAtTime(dbToGain(levelDb), ctx.currentTime)
}

/** The src the tail holds (its URL must stay valid while it plays). */
export const tailSrc = () => (tail && !tail.el.paused ? tail.el.src : '')
