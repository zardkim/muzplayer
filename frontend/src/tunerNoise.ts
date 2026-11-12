// The tuner's hiss between stations (Settings in the tuner, off unless turned on): band-passed white
// noise in a sound context of its own, made on a tap (iPhone), loud the farther the dial is from a
// station. Only while the tuner is showing; never through the player's own sound processing.
let ctx: AudioContext | null = null
let gain: GainNode | null = null

function build() {
  const Ctx = window.AudioContext ?? (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext
  ctx = new Ctx()
  const buffer = ctx.createBuffer(1, ctx.sampleRate * 2, ctx.sampleRate)
  const data = buffer.getChannelData(0)
  for (let i = 0; i < data.length; i++) data[i] = Math.random() * 2 - 1
  const src = ctx.createBufferSource()
  src.buffer = buffer
  src.loop = true
  const band = ctx.createBiquadFilter()
  band.type = 'bandpass'
  band.frequency.value = 2400
  band.Q.value = 0.6
  gain = ctx.createGain()
  gain.gain.value = 0
  src.connect(band).connect(gain).connect(ctx.destination)
  src.start()
}

/** Called from a tap: the context may start only then. */
export function wakeNoise() {
  if (!ctx) build()
  if (ctx?.state !== 'running') void ctx?.resume().catch(() => {})
}

/** 0 (silent) .. 1 (between stations). */
export function setNoise(level: number) {
  if (!ctx || !gain) return
  gain.gain.setTargetAtTime(Math.max(0, Math.min(1, level)) * 0.06, ctx.currentTime, 0.05)
}

export function stopNoise() {
  setNoise(0)
  if (ctx?.state === 'running') window.setTimeout(() => void ctx?.suspend().catch(() => {}), 200)
}
