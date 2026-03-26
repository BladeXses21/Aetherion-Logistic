/**
 * router/index.ts — Vue Router конфігурація з navigation guards (Epic 9.1).
 *
 * Маршрути:
 *   /login    — LoginView (публічний, redirect якщо вже автентифікований)
 *   /         — ChatView (захищений, redirect → /login якщо не автентифікований)
 *   /admin    — AdminView (захищений + role="admin")
 *
 * Navigation guards:
 *   requiresAuth: meta.requiresAuth = true → перевіряємо JWT токен
 *   requiresAdmin: meta.requiresAdmin = true → додатково перевіряємо роль
 */
import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: () => import('@/views/LoginView.vue'),
      meta: { requiresGuest: true },
    },
    {
      path: '/',
      name: 'chat',
      component: () => import('@/views/ChatView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/admin',
      name: 'admin',
      component: () => import('@/views/AdminView.vue'),
      meta: { requiresAuth: true, requiresAdmin: true },
    },
  ],
})

/**
 * Navigation guard — перевірка автентифікації та ролей.
 *
 * Логіка:
 *   1. Якщо маршрут потребує auth → перевіряємо токен у localStorage
 *   2. Якщо маршрут потребує admin → перевіряємо після завантаження профілю
 *   3. Гостьові маршрути (/login) → редірект на / якщо вже залогінений
 */
router.beforeEach(async (to) => {
  const token = localStorage.getItem('aetherion_token')
  const isAuthenticated = !!token

  // Захищений маршрут — потрібна автентифікація
  if (to.meta.requiresAuth && !isAuthenticated) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }

  // Гостьовий маршрут — якщо вже залогінений, редіректимо на головну
  if (to.meta.requiresGuest && isAuthenticated) {
    return { name: 'chat' }
  }

  // Для admin маршрутів — перевіряємо роль через store (lazy load)
  if (to.meta.requiresAdmin && isAuthenticated) {
    const { useAuthStore } = await import('@/stores/auth')
    const { createPinia } = await import('pinia')
    const auth = useAuthStore()

    // Якщо профіль ще не завантажений — завантажуємо
    if (!auth.user && token) {
      await auth.fetchMe()
    }

    if (!auth.isAdmin) {
      return { name: 'chat' }
    }
  }
})

export default router
