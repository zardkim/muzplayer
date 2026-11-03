<script setup lang="ts">
import { useId } from 'vue'
import { Search } from '@lucide/vue'

// A search box: a list page's own (music videos, the library's tabs) and the sheets' (adding songs,
// stations, linking a video...). `large`: the sheets' taller one; Enter emits `submit`.
const props = defineProps<{ placeholder: string; large?: boolean; inputId?: string; maxlength?: number }>()
const emit = defineEmits<{ submit: [] }>()
const model = defineModel<string>({ required: true })
const id = props.inputId ?? useId()
</script>

<template>
  <form
    role="search"
    class="flex min-w-0 items-center gap-2 rounded-full bg-surface px-4 focus-within:ring-2 focus-within:ring-ink"
    :class="large ? 'h-11' : 'h-[38px]'"
    @submit.prevent="emit('submit')"
  >
    <Search :size="large ? 18 : 16" :stroke-width="1.5" class="flex-none text-muted" aria-hidden="true" />
    <label :for="id" class="sr-only">{{ placeholder }}</label>
    <input :id="id" v-model="model" type="search" :maxlength="maxlength ?? 200" :placeholder="placeholder" enterkeyhint="search" class="min-w-0 flex-1 bg-transparent text-[15px] outline-none" />
  </form>
</template>
