/**
 * chat.ts — API клієнт для чатів та SSE стрімінгу (Epic 6).
 *
 * Методи:
 *   chatApi.createChat()   — POST /api/v1/chats
 *   chatApi.sendMessage()  — POST /api/v1/chats/{id}/messages (SSE)
 */
import { apiFetch, BASE_URL } from './client'

export interface CreateChatRequest {
  title?: string
}

export interface ChatResponse {
  id: string
  workspace_id: string
  user_id: string
  title: string
  created_at: string
}

export const chatApi = {
  /**
   * Створює новий чат.
   *
   * @param token - JWT Bearer токен
   * @param data - Назва чату
   * @returns ChatResponse з id нового чату
   */
  createChat(token: string, data: CreateChatRequest = {}): Promise<ChatResponse> {
    return apiFetch<ChatResponse>(
      '/api/v1/chats',
      {
        method: 'POST',
        body: JSON.stringify({ title: data.title ?? 'Новий пошук' }),
      },
      token,
    )
  },

  /**
   * Відправляє повідомлення та стрімить відповідь через SSE.
   *
   * SSE події:
   *   {"type": "token", "content": "..."} — черговий токен відповіді
   *   {"type": "done"}                    — завершення стрімінгу
   *   {"type": "error", "message": "..."}  — помилка
   *
   * @param token - JWT Bearer токен
   * @param chatId - UUID чату
   * @param content - Текст повідомлення
   * @param onToken - Callback для кожного токена
   * @param onDone - Callback при завершенні (отримує повний текст)
   * @param onError - Callback при помилці
   */
  async sendMessage(
    token: string,
    chatId: string,
    content: string,
    onToken: (token: string) => void,
    onDone: (fullContent: string) => void,
    onError: (error: string) => void,
  ): Promise<void> {
    const response = await fetch(`${BASE_URL}/api/v1/chats/${chatId}/messages`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
        'Accept': 'text/event-stream',
      },
      body: JSON.stringify({ content }),
    })

    if (!response.ok) {
      let errorMessage = `HTTP ${response.status}`
      try {
        const errorBody = await response.json()
        errorMessage = errorBody?.detail ?? errorMessage
      } catch {
        // Ігноруємо
      }
      onError(errorMessage)
      return
    }

    const reader = response.body?.getReader()
    if (!reader) {
      onError('Стрімінг недоступний')
      return
    }

    const decoder = new TextDecoder()
    let fullContent = ''
    let buffer = ''

    try {
      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() ?? ''

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          const data = line.slice(6).trim()
          if (!data) continue

          try {
            const event = JSON.parse(data)

            if (event.type === 'token') {
              const tokenText = event.content ?? ''
              fullContent += tokenText
              onToken(tokenText)
            } else if (event.type === 'done') {
              onDone(fullContent)
              return
            } else if (event.type === 'error') {
              onError(event.message ?? 'Невідома помилка агента')
              return
            }
          } catch {
            // Ігноруємо некоректний JSON у SSE
          }
        }
      }
    } finally {
      reader.releaseLock()
    }

    // Якщо стрім завершився без "done" — повертаємо накопичений контент
    if (fullContent) {
      onDone(fullContent)
    }
  },
}
