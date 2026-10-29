import { createRouter, createWebHistory } from 'vue-router'
import { useAuth } from './stores/auth'

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
    { path: '/charts', name: 'charts', component: () => import('./views/ChartsView.vue') },
    { path: '/charts/:id', name: 'chart', component: () => import('./views/ChartView.vue'), props: true },
    { path: '/genres', name: 'genres', component: () => import('./views/GenresView.vue') },
    { path: '/playlists', name: 'playlists', component: () => import('./views/PlaylistsView.vue') },
    { path: '/playlists/:id', name: 'playlist', component: () => import('./views/PlaylistView.vue'), props: true },
    { path: '/favorites', name: 'favorites', component: () => import('./views/FavoritesView.vue') },
    { path: '/history', name: 'history', component: () => import('./views/HistoryView.vue') },
    { path: '/library', name: 'library', component: () => import('./views/LibraryView.vue') },
    { path: '/more', redirect: '/library' },
    { path: '/settings', name: 'settings', component: () => import('./views/SettingsView.vue') },
    { path: '/admin', name: 'admin', component: () => import('./views/AdminView.vue'), meta: { admin: true } },
    { path: '/:rest(.*)', redirect: '/' },
  ],
})

router.beforeEach(async (to) => {
  const auth = useAuth()
  if (!auth.checked) await auth.fetchMe()
  if (to.meta.public) return auth.user ? { name: 'home' } : true
  if (!auth.user) return { name: 'login', query: to.fullPath !== '/' ? { next: to.fullPath } : {} }
  if (to.meta.admin && !auth.user.is_admin) return { name: 'home' }
  return true
})
