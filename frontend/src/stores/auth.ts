/**
 * auth.ts — Pinia store для автентифікації (Epic 9.1).
 *
 * Зберігає JWT токен в localStorage та профіль поточного користувача.
 * Надає методи login(), logout(), fetchMe() для роботи з auth API.
 *
 * Стан автоматично відновлюється при перезавантаженні сторінки через localStorage.
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { authApi } from '@/api/auth'
import type { UserProfile } from '@/api/auth'

export const useAuthStore = defineStore('auth', () => {
  /** JWT access token (зберігається в localStorage для persistence) */
  const token = ref<string | null>(localStorage.getItem('aetherion_token'))

  /** Профіль поточного користувача */
  const user = ref<UserProfile | null>(null)

  /** Чи завантажується стан автентифікації */
  const loading = ref(false)

  /** Чи автентифікований користувач (є токен) */
  const isAuthenticated = computed(() => !!token.value)

  /** Чи є адміністратором */
  const isAdmin = computed(() => user.value?.role === 'admin')

  /**
   * Логін з email та паролем.
   * Зберігає JWT в localStorage та завантажує профіль.
   *
   * @param email - Email адреса
   * @param password - Пароль
   * @throws Error при невірних credentials (401) або мережевій помилці
   */
  async function login(email: string, password: string): Promise<void> {
    loading.value = true
    try {
      const response = await authApi.login({ email, password })
      token.value = response.access_token
      localStorage.setItem('aetherion_token', response.access_token)
      await fetchMe()
    } finally {
      loading.value = false
    }
  }

  /**
   * Виход з системи — очищає токен та профіль.
   */
  function logout(): void {
    token.value = null
    user.value = null
    localStorage.removeItem('aetherion_token')
  }

  /**
   * Завантажує профіль поточного користувача через GET /api/v1/auth/me.
   * Якщо токен невалідний — автоматично виходить.
   */
  async function fetchMe(): Promise<void> {
    if (!token.value) return
    try {
      user.value = await authApi.getMe(token.value)
    } catch {
      // Токен прострочений або невалідний
      logout()
    }
  }

  return {
    token,
    user,
    loading,
    isAuthenticated,
    isAdmin,
    login,
    logout,
    fetchMe,
  }
})
