import { reactive } from 'vue'

/** Runtime settings from the server's /config (.env), filled before the app mounts. */
export const appConfig = reactive({ audiobooks: false, aiBanners: false })
