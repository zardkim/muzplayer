import { watch, type WatchSource } from 'vue'

// Keeps the screen on while `want` is true (Settings → keep the screen on, player open).
// The browser drops the lock when the page is hidden, so it is asked for again on return.
type Sentinel = { release(): Promise<void>; released: boolean }
type WakeLockApi = { request(type: 'screen'): Promise<Sentinel> }

export function useWakeLock(want: WatchSource<boolean>) {
  const api = (navigator as Navigator & { wakeLock?: WakeLockApi }).wakeLock
  if (!api) return // older iOS / browsers: nothing to do
  let lock: Sentinel | null = null
  let wanted = false

  async function sync() {
    const need = wanted && document.visibilityState === 'visible'
    if (need && (!lock || lock.released)) {
      lock = await api!.request('screen').catch(() => null)
    } else if (!need && lock) {
      const l = lock
      lock = null
      await l.release().catch(() => {})
    }
  }
  watch(want, (v) => {
    wanted = v
    void sync()
  }, { immediate: true })
  document.addEventListener('visibilitychange', () => void sync())
}
