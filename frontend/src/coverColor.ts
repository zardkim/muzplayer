import { coverUrl } from './api'

// cover URL -> its average color [r, g, b], shared by every banner and player on the page
const cache = new Map<string, Promise<number[] | null>>()

function average(albumId: number, v?: number): Promise<number[] | null> {
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
          let r = 0, g = 0, b = 0
          for (let i = 0; i < px.length; i += 4) {
            r += px[i]
            g += px[i + 1]
            b += px[i + 2]
          }
          const n = px.length / 4
          resolve([r / n, g / n, b / n])
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
