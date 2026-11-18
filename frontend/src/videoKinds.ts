import { computed, reactive } from 'vue'
import { api } from './api'
import { i18n } from './i18n'

// The kinds music videos are sorted by (video_kinds): the six built in and any an admin added, in
// the admin's order (VideoKindsSheet.vue). A video holds its kind's key; the name is looked up here.
export interface VideoKindItem {
  key: string
  name: string | null // null: a built-in kind, named by the app in the viewer's language
  count: number
  fixed: boolean // "other": where a removed kind's videos go, so it stays
}

export const videoKinds = reactive({ list: [] as VideoKindItem[] })
export const kindKeys = computed(() => videoKinds.list.map((k) => k.key))

let loading: Promise<void> | null = null
/** Once a session (again with fresh: after the admin changed them). */
export function loadVideoKinds(fresh = false): Promise<void> {
  if (!loading || fresh) {
    loading = api<VideoKindItem[]>('/video-kinds')
      .then((list) => void (videoKinds.list = list))
      .catch(() => void (loading = null))
  }
  return loading
}

/** A kind's name: the one given, else a built-in kind's own in this language, else its key. */
export function kindName(key: string): string {
  const kind = videoKinds.list.find((k) => k.key === key)
  if (kind?.name) return kind.name
  const id = `videos.kinds.${key}`
  return i18n.global.te(id) || i18n.global.te(id, 'ko') ? i18n.global.t(id) : key
}

/** The kind picked first when adding videos: music videos, or the first there is. */
export function firstKind(): string {
  return kindKeys.value.includes('mv') ? 'mv' : (kindKeys.value[0] ?? 'other')
}
