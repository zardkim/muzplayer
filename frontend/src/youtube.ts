// YouTube's IFrame player API, loaded once (the video sheet and the video player use it).
export type YTPlayer = { loadVideoById(id: string): void; destroy(): void }
export type YTNamespace = {
  Player: new (el: HTMLElement, opts: object) => YTPlayer
  PlayerState: { PLAYING: number; ENDED: number }
}

export function youtubeApi(): Promise<YTNamespace> {
  const w = window as unknown as { YT?: YTNamespace & { loaded?: number }; onYouTubeIframeAPIReady?: () => void }
  if (w.YT?.Player) return Promise.resolve(w.YT)
  return new Promise((resolve) => {
    const prev = w.onYouTubeIframeAPIReady
    w.onYouTubeIframeAPIReady = () => {
      prev?.()
      resolve(w.YT!)
    }
    if (!document.querySelector('script[data-yt-api]')) {
      const s = document.createElement('script')
      s.src = 'https://www.youtube.com/iframe_api'
      s.dataset.ytApi = ''
      document.head.append(s)
    }
  })
}

export const youtubeThumb = (id: string) => `https://i.ytimg.com/vi/${id}/mqdefault.jpg`
