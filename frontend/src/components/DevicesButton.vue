<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { MonitorSpeaker } from '@lucide/vue'
import { castState } from '../cast'
import { useRemote } from '../stores/remote'
import { useUi } from '../stores/ui'

// Opens the devices sheet (other devices, Chromecast, AirPlay); lit while another device of this
// person plays or a Cast device does.
defineProps<{ size?: number }>()
const { t } = useI18n()
const ui = useUi()
const remote = useRemote()
const elsewhere = computed(() => castState.active || remote.devices.some((d) => d.state?.playing))
</script>

<template>
  <button
    type="button"
    class="grid place-items-center rounded-full hover:bg-surface"
    :class="elsewhere ? 'text-accent' : ''"
    :aria-label="t('devices.title')"
    :title="t('devices.title')"
    @click="ui.devicesOpen = true"
  >
    <MonitorSpeaker :size="size ?? 20" :stroke-width="1.3" />
  </button>
</template>
