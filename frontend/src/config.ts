import { reactive } from 'vue'

/** Runtime settings from the server's /config, filled before the app mounts. */
export const appConfig = reactive({ audiobooks: false, aiBanners: false, youtubeSearch: false, needsSetup: false, transcode: false, aiPlaylists: false, signup: 'off' as 'off' | 'approval' | 'open' })
