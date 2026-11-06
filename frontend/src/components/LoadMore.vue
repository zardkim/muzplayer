<script setup lang="ts">
import { onActivated, onDeactivated, onMounted, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

// "More" under a list that comes page by page. `small`: inside a sheet. `auto`: the next page comes
// by itself as the list's end scrolls near (the library's tabs); the button stays for a tap.
const props = defineProps<{ loading?: boolean; small?: boolean; auto?: boolean }>()
const emit = defineEmits<{ click: [] }>()
const { t } = useI18n()

const el = ref<HTMLButtonElement | null>(null)
let seen = false
let watcher: IntersectionObserver | null = null
function more() {
  if (seen && !props.loading) emit('click')
}
function observe() {
  if (!props.auto || watcher || !el.value || !('IntersectionObserver' in window)) return
  // the page scrolls inside <main>: ahead of it by a screen or so
  watcher = new IntersectionObserver(
    ([e]) => {
      seen = e.isIntersecting
      more()
    },
    { root: el.value.closest('main'), rootMargin: '0px 0px 800px 0px' },
  )
  watcher.observe(el.value)
}
function stop() {
  watcher?.disconnect()
  watcher = null
  seen = false
}
// a page in that still leaves the end in sight: the next one too (a moment later: a page that
// failed to come isn't asked for again at once)
watch(
  () => props.loading,
  (busy) => !busy && window.setTimeout(more, 300),
)
onMounted(observe)
onActivated(observe)
onDeactivated(stop)
onUnmounted(stop)
</script>

<template>
  <button
    ref="el"
    type="button"
    class="mx-auto self-center rounded-full border border-line-strong disabled:opacity-40"
    :class="small ? 'h-10 px-5 text-[14px]' : 'h-11 px-6 text-[15px]'"
    :disabled="loading"
    @click="emit('click')"
  >
    {{ loading ? t('common.loading') : t('common.loadMore') }}
  </button>
</template>
