import type { ComputedRef, InjectionKey } from 'vue'

// Back on a phone (App.vue): whether the page has one, where it goes, and the page headers that show it
// on their own line (PageHeader.vue); while one does, App's separate back line is left out.
export interface PageBack {
  show: ComputedRef<boolean>
  go: () => void
  owners: Set<number>
}
export const PAGE_BACK: InjectionKey<PageBack> = Symbol('page-back')
