import { coverUrl } from './api'

// cover URL -> "r g b" (a darkened average of its cover), shared by every banner on the page
const cache = new Map<string, Promise<string | null>>()

/** The cover's average color, darkened so white text reads on it. Null when there is no cover. */
export function coverColor(albumId: number, v?: number): Promise<string | null> {
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
          // keep the hue, cap the brightness
          const scale = Math.min(1, 110 / Math.max(1, Math.max(r, g, b) / n))
          resolve([r, g, b].map((v) => Math.round((v / n) * scale)).join(' '))
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
