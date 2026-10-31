<script setup lang="ts">
// The muz mark (a tile with "muz", a red dot and hot-pink notes behind) and the name beside it.
// The tile and the word follow the theme: a dark tile on light pages, a light one on the dark theme;
// the dot and notes keep their colours. public/app-icon*.svg and the PWA icons are the same drawing.
withDefaults(defineProps<{ size?: number; wordmark?: boolean }>(), { size: 32, wordmark: true })
</script>

<template>
  <span class="inline-flex items-center gap-2.5">
    <svg :width="size" :height="size" viewBox="0 0 512 512" aria-hidden="true">
      <rect width="512" height="512" rx="112.6" fill="var(--color-ink)" />
      <!-- beamed eighth notes behind the word, in hot pink -->
      <g fill="#FF2D95" opacity="0.68"><g transform="rotate(-10 256 256)"><ellipse cx="168" cy="372" rx="52" ry="38" transform="rotate(-22 168 372)"/><ellipse cx="352" cy="334" rx="52" ry="38" transform="rotate(-22 352 334)"/><rect x="196" y="120" width="24" height="250"/><rect x="380" y="84" width="24" height="248"/><path d="M196 120 L404 84 L404 138 L196 174 Z"/></g></g>
      <path transform="translate(48.51 301.81) scale(0.18473)" fill="var(--color-bg)" d="M70 0V-496H194V-442H212Q225 -467 255.0 -485.5Q285 -504 334 -504Q387 -504 419.0 -483.5Q451 -463 468 -430H486Q503 -462 534.0 -483.0Q565 -504 622 -504Q668 -504 705.5 -484.5Q743 -465 765.5 -425.5Q788 -386 788 -326V0H662V-317Q662 -358 641.0 -378.5Q620 -399 582 -399Q539 -399 515.5 -371.5Q492 -344 492 -293V0H366V-317Q366 -358 345.0 -378.5Q324 -399 286 -399Q243 -399 219.5 -371.5Q196 -344 196 -293V0ZM1093 8Q1035 8 991.5 -18.5Q948 -45 924.0 -92.0Q900 -139 900 -200V-496H1026V-210Q1026 -154 1053.5 -126.0Q1081 -98 1132 -98Q1190 -98 1222.0 -136.5Q1254 -175 1254 -244V-496H1380V0H1256V-65H1238Q1226 -40 1193.0 -16.0Q1160 8 1093 8ZM1482 0V-150L1754 -376V-392H1492V-496H1892V-346L1620 -120V-104H1900V0Z" />
      <circle cx="429.75" cy="282.48" r="20.81" fill="#E8432A" />
    </svg>
    <span v-if="wordmark" class="font-display tracking-tight" :style="{ fontSize: `${Math.round(size * 0.68)}px` }">
      <b>muz</b><span class="text-muted">player</span>
    </span>
  </span>
</template>
