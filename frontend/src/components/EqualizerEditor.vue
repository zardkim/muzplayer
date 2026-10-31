<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { EQ_BANDS, EQ_PRESETS } from '../audioGraph'
import { useUi } from '../stores/ui'

// Settings → sound: a preset, or ten sliders (moving one makes it "custom")
const { t } = useI18n()
const ui = useUi()
const prefs = computed(() => ui.playerPrefs)
const gains = computed(() => (prefs.value.eqPreset === 'custom' ? prefs.value.eqGains : (EQ_PRESETS[prefs.value.eqPreset] ?? EQ_PRESETS.flat)))
const label = (f: number) => (f >= 1000 ? `${f / 1000}k` : String(f))

function pick(preset: string) {
  if (preset === 'custom') prefs.value.eqGains = [...gains.value]
  prefs.value.eqPreset = preset
}
function set(i: number, db: number) {
  const next = [...gains.value]
  next[i] = db
  prefs.value.eqGains = next
  prefs.value.eqPreset = 'custom'
}
</script>

<template>
  <div class="flex flex-col gap-3" :class="prefs.eq ? '' : 'pointer-events-none opacity-40'">
    <div class="flex flex-wrap gap-1.5" role="group" :aria-label="t('settings.eqPreset')">
      <button
        v-for="p in [...Object.keys(EQ_PRESETS), 'custom']"
        :key="p"
        type="button"
        class="h-8 rounded-full border px-3 text-[13px]"
        :class="prefs.eqPreset === p ? 'border-ink bg-ink text-on-ink' : 'border-line-strong'"
        :aria-pressed="prefs.eqPreset === p"
        @click="pick(p)"
      >
        {{ t(`settings.eq_${p}`) }}
      </button>
    </div>
    <div class="flex h-44 items-stretch justify-between gap-1 rounded-2xl bg-surface px-2 py-3">
      <label v-for="(f, i) in EQ_BANDS" :key="f" class="flex flex-1 flex-col items-center gap-1 text-[11px] text-muted">
        <span class="font-display text-ink">{{ gains[i] > 0 ? '+' : '' }}{{ gains[i] }}</span>
        <input
          type="range"
          min="-12"
          max="12"
          step="1"
          :value="gains[i]"
          class="w-5 flex-1 accent-accent [direction:rtl] [writing-mode:vertical-lr]"
          :aria-label="`${label(f)}Hz`"
          @input="(e) => set(i, Number((e.target as HTMLInputElement).value))"
        />
        <span class="font-display">{{ label(f) }}</span>
      </label>
    </div>
  </div>
</template>
