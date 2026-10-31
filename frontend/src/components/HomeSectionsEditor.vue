<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { ArrowDown, ArrowUp } from '@lucide/vue'
import { errorMessage } from '../i18n'
import { homeSections, type HomeSection } from '../homeSections'
import { useAuth } from '../stores/auth'
import { useUi } from '../stores/ui'

// Settings → home screen: each row on or off, moved up or down; saved to the account at once
const { t } = useI18n()
const auth = useAuth()
const ui = useUi()
const sections = computed(() => homeSections(auth.user?.home_sections))

function save(next: HomeSection[]) {
  if (auth.user) auth.user.home_sections = next // shows at once; the server keeps it
  auth.updateSettings({ home_sections: next }).catch((e) => ui.notify(errorMessage(e), true))
}
function toggle(i: number) {
  save(sections.value.map((s, k) => (k === i ? { ...s, on: !s.on } : s)))
}
function move(i: number, dir: -1 | 1) {
  const next = [...sections.value]
  ;[next[i], next[i + dir]] = [next[i + dir], next[i]]
  save(next)
}
</script>

<template>
  <ul class="flex flex-col divide-y divide-line">
    <li v-for="(s, i) in sections" :key="s.key" class="flex items-center gap-2 py-2">
      <label class="flex flex-1 cursor-pointer items-center gap-3">
        <input type="checkbox" class="size-[18px] accent-accent" :checked="s.on" @change="toggle(i)" />
        <span class="text-[16px]" :class="s.on ? '' : 'text-muted'">{{ t(`home.section_${s.key}`) }}</span>
      </label>
      <button type="button" class="grid size-9 place-items-center rounded-full hover:bg-surface disabled:opacity-30" :disabled="i === 0" :aria-label="t('common.moveUp')" @click="move(i, -1)">
        <ArrowUp :size="17" :stroke-width="1.6" />
      </button>
      <button type="button" class="grid size-9 place-items-center rounded-full hover:bg-surface disabled:opacity-30" :disabled="i === sections.length - 1" :aria-label="t('common.moveDown')" @click="move(i, 1)">
        <ArrowDown :size="17" :stroke-width="1.6" />
      </button>
    </li>
  </ul>
</template>
