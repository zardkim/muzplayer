import { createRouter, createWebHistory, type RouteLocationRaw } from 'vue-router'
import { appConfig } from './config'
import { useAuth } from './stores/auth'

// the library menu's tabs (LibraryHeader.vue), in order
export const LIBRARY_ROUTES = ['albums', 'artists', 'tracks', 'genres', 'folders'] as const
export type LibraryRoute = (typeof LIBRARY_ROUTES)[number]

export const router = createRouter({
  history: createWebHistory(),
  scrollBehavior: (_to, _from, saved) => saved ?? { top: 0 },
  routes: [
    { path: '/login', name: 'login', component: () => import('./views/LoginView.vue'), meta: { public: true } },
    { path: '/', name: 'home', component: () => import('./views/HomeView.vue') },
    { path: '/search', name: 'search', component: () => import('./views/SearchView.vue') },
    { path: '/tracks', name: 'tracks', component: () => import('./views/TracksView.vue') },
    { path: '/albums', name: 'albums', component: () => import('./views/AlbumsView.vue') },
    { path: '/albums/:id', name: 'album', component: () => import('./views/AlbumView.vue'), props: true },
    { path: '/artists', name: 'artists', component: () => import('./views/ArtistsView.vue') },
    { path: '/artists/:id', name: 'artist', component: () => import('./views/ArtistView.vue'), props: true },
    { path: '/radio', name: 'radio', component: () => import('./views/RadioView.vue') },
    { path: '/videos', name: 'videos', component: () => import('./views/VideosView.vue') },
    { path: '/video-playlists/:id', name: 'video-playlist', component: () => import('./views/VideoPlaylistView.vue'), props: true },
    { path: '/charts', name: 'charts', component: () => import('./views/CollectionsView.vue') },
    { path: '/charts/list', name: 'chart-list', component: () => import('./views/ChartsView.vue') },
    { path: '/charts/:id', name: 'chart', component: () => import('./views/ChartView.vue'), props: true },
    { path: '/books', name: 'books', component: () => import('./views/BooksView.vue'), meta: { books: true } },
    { path: '/books/:id', name: 'book', component: () => import('./views/BookView.vue'), props: true, meta: { books: true } },
    { path: '/genres', name: 'genres', component: () => import('./views/GenresView.vue') },
    { path: '/folders', name: 'folders', component: () => import('./views/FoldersView.vue') },
    { path: '/playing', name: 'playing', component: () => import('./views/PlayingView.vue') },
    { path: '/playlists', name: 'playlists', component: () => import('./views/PlaylistsView.vue') },
    { path: '/playlists/:id', name: 'playlist', component: () => import('./views/PlaylistView.vue'), props: true },
    { path: '/mixes/:mixKey', name: 'mix', component: () => import('./views/MixView.vue'), props: true },
    { path: '/favorites', name: 'favorites', component: () => import('./views/FavoritesView.vue') },
    { path: '/history', name: 'history', component: () => import('./views/HistoryView.vue') },
    { path: '/downloads', name: 'downloads', component: () => import('./views/DownloadsView.vue') },
    { path: '/library', name: 'library', component: () => import('./views/LibraryView.vue') },
    { path: '/more', redirect: '/library' },
    { path: '/settings/:section?', name: 'settings', component: () => import('./views/SettingsView.vue'), props: true },
    { path: '/admin/logs', name: 'logs', component: () => import('./views/LogsView.vue'), meta: { admin: true } },
    { path: '/admin/stats', name: 'stats', component: () => import('./views/StatsView.vue'), meta: { admin: true } },
    { path: '/admin/:section?', name: 'admin', component: () => import('./views/AdminView.vue'), meta: { admin: true }, props: true },
    { path: '/:rest(.*)', redirect: '/' },
  ],
})

router.beforeEach(async (to) => {
  const auth = useAuth()
  if (!auth.checked) await auth.fetchMe()
  // signed in, the login page is only for adding another account (user switching)
  if (to.meta.public) return auth.user ? { name: 'home' } : true
  if (!auth.user) return { name: 'login', query: to.fullPath !== '/' ? { next: to.fullPath } : {} }
  if (to.meta.admin && !auth.user.is_admin) return { name: 'home' }
  if (to.meta.books && !appConfig.audiobooks) return { name: 'home' }
  return true
})

// Back within the app; a page opened directly (a link, a reload with no earlier page) goes to fallback.
export function goBack(fallback: RouteLocationRaw = '/') {
  if (window.history.state?.back) router.back()
  else router.push(fallback)
}
