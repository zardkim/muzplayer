import { coverUrl } from './api'

// cover URL -> its average colours [r, g, b]: of all of it, and of its top and bottom halves; shared
// by every banner and player on the page
interface Averages { all: number[]; top: number[]; bottom: number[] }
const cache = new Map<string, Promise<Averages | null>>()

async function average(albumId: number, v?: number): Promise<number[] | null> {
  return (await averages(albumId, v))?.all ?? null
}

function averages(albumId: number, v?: number): Promise<Averages | null> {
  const url = coverUrl(albumId, 'thumb', v)
  let hit = cache.get(url)
  if (!hit) {
    hit = new Promise((resolve) => {
      const img = new Image()
      img.onload = () => {
        try {
          const canvas = document.createElement('canvas')
          canvas.width = canvas.height = 8
          const ctx = canvas.getContext('2d', { willReadFrequently: true })!
          ctx.drawImage(img, 0, 0, 8, 8)
          const px = ctx.getImageData(0, 0, 8, 8).data
          const mean = (from: number, to: number) => {
            let r = 0, g = 0, b = 0
            for (let i = from; i < to; i += 4) {
              r += px[i]
              g += px[i + 1]
              b += px[i + 2]
            }
            const n = (to - from) / 4
            return [r / n, g / n, b / n]
          }
          const half = px.length / 2 // rows 0-3, rows 4-7
          resolve({ all: mean(0, px.length), top: mean(0, half), bottom: mean(half, px.length) })
        } catch {
          resolve(null)
        }
      }
      img.onerror = () => resolve(null)
      img.src = url
    })
    cache.set(url, hit)
  }
  return hit
}

/** The cover's average color, darkened so white text reads on it ("r g b"). Null when there is no cover. */
export async function coverColor(albumId: number, v?: number): Promise<string | null> {
  const avg = await average(albumId, v)
  if (!avg) return null
  const scale = Math.min(1, 110 / Math.max(1, ...avg)) // keep the hue, cap the brightness
  return avg.map((c) => Math.round(c * scale)).join(' ')
}

/** The cover's plain average color (CSS rgb()), for the players' soft background glow. */
export async function coverGlow(albumId: number, v?: number): Promise<string | null> {
  const avg = await average(albumId, v)
  return avg ? `rgb(${avg.map(Math.round).join(' ')})` : null
}

/** A soft wash of the cover's colour for the lyrics view: see-through, strongest in the middle and
 *  fading out at every edge (the text keeps the page's own colours). Null when there is no cover. */
export async function coverWash(albumId: number, v?: number): Promise<string | null> {
  const avg = await average(albumId, v)
  if (!avg) return null
  const rgb = avg.map(Math.round).join(' ')
  return `radial-gradient(closest-side, rgb(${rgb} / 0.24) 0%, rgb(${rgb} / 0.1) 60%, rgb(${rgb} / 0) 100%)`
}

/** The phone player's background: the cover's top and bottom colours, deep enough for white text
 *  (the bottom one darker still). Null when there is no cover. */
export async function coverShades(albumId: number, v?: number): Promise<{ top: string; bottom: string } | null> {
  const avg = await averages(albumId, v)
  if (!avg) return null
  const deep = (c: number[], most: number) => {
    const scale = Math.min(1, most / Math.max(1, ...c)) // keep the hue, cap the brightness
    return `rgb(${c.map((x) => Math.round(x * scale)).join(' ')})`
  }
  return { top: deep(avg.top, 120), bottom: deep(avg.bottom, 62) }
}
