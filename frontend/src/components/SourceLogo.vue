<script setup lang="ts">
import { computed } from 'vue'
import { sourceLogo } from '../format'

// A chart site's logo beside its name (멜론, 벅스, 지니, 올레, 빌보드); nothing for other sources.
const props = withDefaults(defineProps<{ source: string; size?: number }>(), { size: 18 })
const src = computed(() => sourceLogo(props.source))
</script>

<template>
  <img v-if="src" :src="src" alt="" :width="size" :height="size" class="flex-none rounded-[22%]" :style="{ width: `${size}px`, height: `${size}px` }" />
</template>
