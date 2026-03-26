/**
 * chat.ts — Pinia store для управління чатами та повідомленнями (Epic 6).
 *
 * Зберігає поточний chat_id та список повідомлень.
 * Управляє SSE стрімінгом відповіді від агента.
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { chatApi } from '@/api/chat'
import { useAuthStore } from '@/stores/auth'

export interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  status: 'complete' | 'streaming' | 'incomplete'
  createdAt: string
}

export const useChatStore = defineStore('chat', () => {
  /** UUID поточного активного чату */
  const chatId = ref<string | null>(null)

  /** Список повідомлень поточного чату */
  const messages = ref<Message[]>([])

  /** Поточний стрімінговий текст (під час отримання відповіді) */
  const streamingContent = ref<string>('')

  /** Чи зараз стрімить відповідь */
  const isStreaming = ref(false)

  /** Помилка якщо є */
  const error = ref<string | null>(null)

  /**
   * Ініціалізує новий чат через POST /api/v1/chats.
   * Очищає попередню历ію.
   *
   * @param title - Назва чату
   */
  async function startNewChat(title = 'Новий пошук'): Promise<void> {
    const auth = useAuthStore()
    if (!auth.token) return

    const chat = await chatApi.createChat(auth.token, { title })
    chatId.value = chat.id
    messages.value = []
    streamingContent.value = ''
    error.value = null
  }

  /**
   * Відправляє повідомлення та стрімить відповідь агента через SSE.
   *
   * Алгоритм:
   *   1. Додаємо user-повідомлення у messages[]
   *   2. POST /api/v1/chats/{id}/messages → SSE стрім
   *   3. Акумулюємо токени в streamingContent
   *   4. Після "done" — переносимо в messages[] як assistant
   *
   * @param content - Текст повідомлення від користувача
   */
  async function sendMessage(content: string): Promise<void> {
    const auth = useAuthStore()
    if (!auth.token || !chatId.value) return

    // Якщо чат не ініціалізований — стартуємо
    if (!chatId.value) {
      await startNewChat()
    }

    error.value = null

    // Додаємо повідомлення користувача в UI одразу
    const userMsg: Message = {
      id: `user-${Date.now()}`,
      role: 'user',
      content,
      status: 'complete',
      createdAt: new Date().toISOString(),
    }
    messages.value.push(userMsg)

    // Починаємо стрімінг
    isStreaming.value = true
    streamingContent.value = ''

    try {
      await chatApi.sendMessage(
        auth.token,
        chatId.value,
        content,
        (token) => {
          // Обробник кожного токена
          streamingContent.value += token
        },
        (fullContent) => {
          // Завершення стрімінгу — переносимо у messages
          messages.value.push({
            id: `assistant-${Date.now()}`,
            role: 'assistant',
            content: fullContent,
            status: 'complete',
            createdAt: new Date().toISOString(),
          })
          streamingContent.value = ''
          isStreaming.value = false
        },
        (err) => {
          error.value = err
          isStreaming.value = false
        },
      )
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Невідома помилка'
      isStreaming.value = false
    }
  }

  /**
   * Скидає весь стан чату (для старту нового розмови).
   */
  function resetChat(): void {
    chatId.value = null
    messages.value = []
    streamingContent.value = ''
    isStreaming.value = false
    error.value = null
  }

  return {
    chatId,
    messages,
    streamingContent,
    isStreaming,
    error,
    startNewChat,
    sendMessage,
    resetChat,
  }
})
