// The rows of the home screen, in their default order. Each person can hide rows and change the
// order (Settings → home screen); that is kept on the server, so every device shows the same.
export const HOME_KEYS = ['banners', 'playlists', 'stations', 'onThisDay', 'mixes', 'quick', 'books', 'newAlbums', 'recentVideos', 'likedVideos'] as const
export type HomeKey = (typeof HOME_KEYS)[number]
export type HomeSection = { key: HomeKey; on: boolean }

/** The saved order with unknown rows dropped; rows added since are put in their default place
 *  (after the row they follow by default) and shown. */
export function homeSections(saved: { key: string; on: boolean }[] | null | undefined): HomeSection[] {
  const out = (saved ?? []).filter((s): s is HomeSection => (HOME_KEYS as readonly string[]).includes(s.key))
  HOME_KEYS.forEach((key, i) => {
    if (out.some((s) => s.key === key)) return
    const before = i ? out.findIndex((s) => s.key === HOME_KEYS[i - 1]) : -1
    out.splice(before + 1, 0, { key, on: true })
  })
  return out
}
