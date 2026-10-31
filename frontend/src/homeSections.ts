// The rows of the home screen, in their default order. Each person can hide rows and change the
// order (Settings → home screen); that is kept on the server, so every device shows the same.
export const HOME_KEYS = ['banners', 'onThisDay', 'mixes', 'quick', 'books', 'newAlbums'] as const
export type HomeKey = (typeof HOME_KEYS)[number]
export type HomeSection = { key: HomeKey; on: boolean }

/** The saved order with unknown rows dropped and rows added since appended (shown). */
export function homeSections(saved: { key: string; on: boolean }[] | null | undefined): HomeSection[] {
  const known = (saved ?? []).filter((s): s is HomeSection => (HOME_KEYS as readonly string[]).includes(s.key))
  const missing = HOME_KEYS.filter((k) => !known.some((s) => s.key === k)).map((key) => ({ key, on: true }))
  return [...known, ...missing]
}
