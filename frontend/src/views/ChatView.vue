<template>
  <!-- Основна сторінка чату — дизайн як у Grok AI (темна тема) -->
  <div class="min-h-screen bg-background flex flex-col">

    <!-- Хедер -->
    <header class="border-b border-border/50 px-4 py-3 flex items-center justify-between shrink-0">
      <div class="flex items-center gap-3">
        <div class="w-7 h-7 rounded-lg bg-primary flex items-center justify-center">
          <span class="text-primary-foreground font-bold text-xs">A</span>
        </div>
        <span class="font-semibold text-foreground">Aetherion</span>
        <Badge variant="outline" class="text-xs text-muted-foreground border-border/50">
          AI пошук вантажів
        </Badge>
      </div>

      <div class="flex items-center gap-2">
        <!-- Кнопка новий чат -->
        <Button
          variant="ghost"
          size="sm"
          @click="handleNewChat"
          :disabled="chatStore.isStreaming"
          class="text-muted-foreground hover:text-foreground"
        >
          <PlusIcon class="w-4 h-4 mr-1" />
          Новий пошук
        </Button>

        <!-- Адмін панель (тільки для адміна) -->
        <Button
          v-if="auth.isAdmin"
          variant="ghost"
          size="sm"
          @click="$router.push('/admin')"
          class="text-muted-foreground hover:text-foreground"
        >
          <SettingsIcon class="w-4 h-4" />
        </Button>

        <!-- Профіль / вихід — dropdown меню -->
        <DropdownMenuRoot>
          <DropdownMenuTrigger as-child>
            <Button
              variant="ghost"
              size="sm"
              class="text-muted-foreground hover:text-foreground"
            >
              <Avatar class="w-6 h-6">
                <AvatarFallback class="text-xs bg-secondary">
                  {{ userInitial }}
                </AvatarFallback>
              </Avatar>
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuPortal>
            <DropdownMenuContent
              align="end"
              :side-offset="6"
              class="z-50 min-w-44 rounded-lg border border-border bg-card shadow-md p-1 text-sm"
            >
              <!-- Email поточного користувача -->
              <div class="px-2 py-1.5 text-xs text-muted-foreground truncate max-w-48">
                {{ auth.user?.email }}
              </div>
              <DropdownMenuSeparator class="my-1 h-px bg-border/50" />
              <!-- Вихід -->
              <DropdownMenuItem
                class="flex items-center gap-2 px-2 py-1.5 rounded-md cursor-pointer text-destructive hover:bg-destructive/10 outline-none"
                @click="handleLogout"
              >
                <LogOutIcon class="w-3.5 h-3.5" />
                Вийти
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenuPortal>
        </DropdownMenuRoot>
      </div>
    </header>

    <!-- Область повідомлень -->
    <ScrollArea ref="scrollAreaRef" class="flex-1 px-4">
      <div class="max-w-3xl mx-auto py-6 space-y-6">

        <!-- Привітання якщо немає повідомлень -->
        <div v-if="chatStore.messages.length === 0 && !chatStore.isStreaming" class="text-center py-16 space-y-4">
          <div class="w-16 h-16 rounded-2xl bg-secondary flex items-center justify-center mx-auto">
            <TruckIcon class="w-8 h-8 text-muted-foreground" />
          </div>
          <h2 class="text-xl font-semibold text-foreground">Пошук вантажів</h2>
          <p class="text-muted-foreground max-w-sm mx-auto text-sm">
            Опишіть що шукаєте — напрямок, тип кузова, вагу. Я знайду підходящі вантажі на Lardi-Trans.
          </p>

          <!-- Підказки -->
          <div class="flex flex-wrap gap-2 justify-center mt-4">
            <button
              v-for="hint in HINTS"
              :key="hint"
              @click="inputText = hint"
              class="px-3 py-1.5 text-sm rounded-full border border-border/50 text-muted-foreground hover:text-foreground hover:border-border transition-colors"
            >
              {{ hint }}
            </button>
          </div>
        </div>

        <!-- Список повідомлень -->
        <template v-for="msg in chatStore.messages" :key="msg.id">
          <!-- User повідомлення -->
          <div v-if="msg.role === 'user'" class="flex justify-end">
            <div class="max-w-[80%] bg-secondary rounded-2xl rounded-tr-sm px-4 py-2.5 text-sm text-foreground">
              {{ msg.content }}
            </div>
          </div>

          <!-- Assistant повідомлення -->
          <div v-else class="flex gap-3">
            <div class="w-7 h-7 rounded-lg bg-primary flex items-center justify-center shrink-0 mt-0.5">
              <span class="text-primary-foreground font-bold text-xs">A</span>
            </div>
            <div class="flex-1 min-w-0">
              <AssistantMessage :content="msg.content" />
            </div>
          </div>
        </template>

        <!-- Стрімінг відповідь (поточна) -->
        <div v-if="chatStore.isStreaming || chatStore.streamingContent" class="flex gap-3">
          <div class="w-7 h-7 rounded-lg bg-primary flex items-center justify-center shrink-0 mt-0.5">
            <span class="text-primary-foreground font-bold text-xs">A</span>
          </div>
          <div class="flex-1 min-w-0">
            <AssistantMessage
              v-if="chatStore.streamingContent"
              :content="chatStore.streamingContent"
              :streaming="true"
            />
            <!-- Анімований курсор поки чекаємо першого токена -->
            <div v-else class="flex gap-1 py-2">
              <div class="w-2 h-2 bg-muted-foreground rounded-full animate-bounce [animation-delay:-0.3s]" />
              <div class="w-2 h-2 bg-muted-foreground rounded-full animate-bounce [animation-delay:-0.15s]" />
              <div class="w-2 h-2 bg-muted-foreground rounded-full animate-bounce" />
            </div>
          </div>
        </div>

        <!-- Помилка -->
        <div v-if="chatStore.error" class="flex gap-3">
          <div class="w-7 h-7 rounded-lg bg-destructive/20 flex items-center justify-center shrink-0">
            <AlertCircleIcon class="w-4 h-4 text-destructive" />
          </div>
          <p class="text-sm text-destructive mt-1">{{ chatStore.error }}</p>
        </div>

        <!-- Якір для автоскролу -->
        <div ref="messagesEndRef" />
      </div>
    </ScrollArea>

    <!-- Поле вводу -->
    <div class="border-t border-border/50 px-4 py-4 shrink-0">
      <div class="max-w-3xl mx-auto">
        <div class="flex gap-2 items-end bg-secondary/50 rounded-2xl border border-border/50 px-4 py-3">
          <textarea
            ref="textareaRef"
            v-model="inputText"
            @keydown.enter.exact.prevent="handleSend"
            @input="autoResize"
            placeholder="Опишіть вантаж або маршрут... (Enter — відправити)"
            :disabled="chatStore.isStreaming"
            rows="1"
            class="flex-1 bg-transparent text-sm text-foreground placeholder:text-muted-foreground resize-none outline-none max-h-32 leading-relaxed"
          />
          <Button
            size="sm"
            @click="handleSend"
            :disabled="!inputText.trim() || chatStore.isStreaming"
            class="shrink-0 rounded-xl h-8 w-8 p-0"
          >
            <SendIcon class="w-4 h-4" />
          </Button>
        </div>
        <p class="text-xs text-muted-foreground/50 text-center mt-2">
          Shift+Enter — новий рядок
        </p>
      </div>
    </div>

  </div>
</template>

<script setup lang="ts">
/**
 * ChatView — основна сторінка чату з AI асистентом.
 *
 * Функціонал:
 *   - Відправка повідомлень та отримання SSE відповіді
 *   - Автоскрол до останнього повідомлення
 *   - Авторесайз textarea
 *   - Відображення cargo-карток в AssistantMessage
 */
import { ref, computed, nextTick, watch, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useChatStore } from '@/stores/chat'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import {
  PlusIcon,
  SendIcon,
  TruckIcon,
  SettingsIcon,
  AlertCircleIcon,
  LogOutIcon,
} from 'lucide-vue-next'
import {
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuPortal,
  DropdownMenuRoot,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from 'reka-ui'
import AssistantMessage from '@/components/chat/AssistantMessage.vue'

const router = useRouter()
const auth = useAuthStore()
const chatStore = useChatStore()

const inputText = ref('')
const textareaRef = ref<HTMLTextAreaElement | null>(null)
const messagesEndRef = ref<HTMLDivElement | null>(null)
const scrollAreaRef = ref<InstanceType<typeof ScrollArea> | null>(null)

/** Перша літера email для аватара */
const userInitial = computed(() =>
  auth.user?.email?.charAt(0).toUpperCase() ?? '?'
)

/** Підказки для початку */
const HINTS = [
  'Київ → Одеса, тент',
  'Польща → Україна, рефрижератор',
  'Харків → Варшава, зерновоз',
  'Тільки від власника вантажу',
]

/**
 * Ініціалізація — завантажуємо профіль та стартуємо чат.
 */
onMounted(async () => {
  if (!auth.user) {
    await auth.fetchMe()
  }
  await chatStore.startNewChat()
})

/**
 * Відправляємо повідомлення якщо є текст.
 */
async function handleSend() {
  const text = inputText.value.trim()
  if (!text || chatStore.isStreaming) return

  inputText.value = ''
  await nextTick()
  autoResize()

  await chatStore.sendMessage(text)
}

/**
 * Стартуємо новий чат (скидаємо поточний).
 */
async function handleNewChat() {
  chatStore.resetChat()
  await chatStore.startNewChat()
  inputText.value = ''
}

/**
 * Виходимо з системи.
 */
function handleLogout() {
  auth.logout()
  router.push('/login')
}

/**
 * Автоматично змінює висоту textarea відповідно до вмісту.
 */
function autoResize() {
  if (textareaRef.value) {
    textareaRef.value.style.height = 'auto'
    textareaRef.value.style.height = `${textareaRef.value.scrollHeight}px`
  }
}

/**
 * Скролить до останнього повідомлення після кожного оновлення.
 */
watch(
  [() => chatStore.messages.length, () => chatStore.streamingContent],
  async () => {
    await nextTick()
    messagesEndRef.value?.scrollIntoView({ behavior: 'smooth' })
  },
)
</script>
