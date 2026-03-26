/**
 * auth.ts — API клієнт для автентифікації (Epic 9.1).
 *
 * Методи:
 *   authApi.login()  — POST /api/v1/auth/login → TokenResponse
 *   authApi.getMe()  — GET /api/v1/auth/me → UserProfile
 */
import { apiFetch } from './client'

export interface LoginRequest {
  email: string
  password: string
}

export interface TokenResponse {
  access_token: string
  token_type: string
  expires_in: number
}

export interface UserProfile {
  id: string
  email: string
  role: string
  is_active: boolean
  created_at: string
}

export const authApi = {
  /**
   * Виконує логін та повертає JWT токен.
   *
   * @param credentials - email та password
   * @returns TokenResponse з access_token
   * @throws Error при невірних credentials (401)
   */
  login(credentials: LoginRequest): Promise<TokenResponse> {
    return apiFetch<TokenResponse>('/api/v1/auth/login', {
      method: 'POST',
      body: JSON.stringify(credentials),
    })
  },

  /**
   * Отримує профіль поточного користувача по JWT токену.
   *
   * @param token - JWT Bearer токен
   * @returns UserProfile
   * @throws Error якщо токен невалідний (401)
   */
  getMe(token: string): Promise<UserProfile> {
    return apiFetch<UserProfile>('/api/v1/auth/me', {}, token)
  },
}
