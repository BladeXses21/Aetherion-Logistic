/**
 * client.ts — Базовий HTTP клієнт для API запитів.
 *
 * Надає функцію apiFetch() яка автоматично:
 *   - Додає Authorization: Bearer токен
 *   - Встановлює Content-Type: application/json
 *   - Кидає помилку при HTTP 4xx/5xx
 *
 * BASE_URL береться з VITE_API_URL змінної середовища (за замовчуванням http://localhost:8000).
 */

// У Docker (nginx) — порожній рядок, nginx проксує /api/ сам.
// У локальній розробці — встановлюємо VITE_API_URL=http://localhost:8000 у .env
export const BASE_URL = import.meta.env.VITE_API_URL ?? ''

/**
 * Базова функція для API запитів з автоматичним JSON парсингом.
 *
 * @param path - Шлях (без BASE_URL), наприклад "/api/v1/auth/login"
 * @param options - fetch options (method, body, headers)
 * @param token - JWT Bearer токен (опційно)
 * @returns Розпарсений JSON або null для 204 відповідей
 * @throws Error з message якщо HTTP статус >= 400
 */
export async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
  token?: string | null,
): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string> ?? {}),
  }

  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  const response = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers,
  })

  if (!response.ok) {
    let errorMessage = `HTTP ${response.status}`
    try {
      const errorBody = await response.json()
      errorMessage = errorBody?.detail ?? errorBody?.message ?? errorMessage
    } catch {
      // Ігноруємо якщо тіло не JSON
    }
    throw new Error(errorMessage)
  }

  // 204 No Content — повертаємо null
  if (response.status === 204) {
    return null as T
  }

  return response.json() as Promise<T>
}
