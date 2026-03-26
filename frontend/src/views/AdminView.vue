<template>
  <!-- Адміністративна панель — управління користувачами та системою -->
  <div class="min-h-screen bg-background">

    <!-- Діалог введення Admin API Key -->
    <DialogRoot :open="showKeyDialog" @update:open="onKeyDialogOpenChange">
      <DialogPortal>
        <DialogOverlay class="fixed inset-0 z-50 bg-black/60 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0" />
        <DialogContent
          class="fixed left-1/2 top-1/2 z-50 w-full max-w-md -translate-x-1/2 -translate-y-1/2 rounded-xl border border-border bg-card p-6 shadow-xl focus:outline-none"
          @interact-outside.prevent
          @escape-key-down.prevent
        >
          <h2 class="text-base font-semibold text-foreground mb-1">Admin API Key</h2>
          <p class="text-sm text-muted-foreground mb-4">
            Введіть ключ для доступу до адміністративної панелі.
          </p>
          <Input
            v-model="keyInput"
            type="password"
            placeholder="Введіть ключ..."
            class="mb-2"
            @keydown.enter="handleKeySubmit"
            autofocus
          />
          <div v-if="keyError" class="text-sm text-destructive mb-3">{{ keyError }}</div>
          <div class="flex justify-end gap-2 mt-4">
            <Button variant="ghost" @click="handleKeyCancel">Скасувати</Button>
            <Button @click="handleKeySubmit" :disabled="!keyInput.trim()">Підтвердити</Button>
          </div>
        </DialogContent>
      </DialogPortal>
    </DialogRoot>

    <!-- Хедер -->
    <header class="border-b border-border/50 px-6 py-4 flex items-center justify-between">
      <div class="flex items-center gap-3">
        <Button variant="ghost" size="sm" @click="$router.push('/')" class="text-muted-foreground">
          <ArrowLeftIcon class="w-4 h-4 mr-1" />
          Назад
        </Button>
        <Separator orientation="vertical" class="h-5" />
        <h1 class="font-semibold text-foreground">Адмін панель</h1>
      </div>
      <div class="flex items-center gap-3">
        <Badge variant="outline" class="text-xs text-muted-foreground">
          {{ auth.user?.email }}
        </Badge>
        <!-- Кнопка зміни ключа -->
        <Button variant="ghost" size="sm" class="text-xs text-muted-foreground" @click="openChangeKey">
          Змінити ключ
        </Button>
      </div>
    </header>

    <div class="max-w-5xl mx-auto px-6 py-8 space-y-8">

      <!-- Секція: Управління користувачами -->
      <section class="space-y-4">
        <div class="flex items-center justify-between">
          <div>
            <h2 class="text-lg font-semibold text-foreground">Користувачі (Whitelist)</h2>
            <p class="text-sm text-muted-foreground">Управляйте доступом до системи</p>
          </div>
          <Button size="sm" @click="showCreateForm = !showCreateForm">
            <PlusIcon class="w-4 h-4 mr-1" />
            Додати
          </Button>
        </div>

        <!-- Форма створення користувача -->
        <Card v-if="showCreateForm" class="border-border/50 bg-card">
          <CardHeader>
            <CardTitle class="text-base">Новий користувач</CardTitle>
          </CardHeader>
          <CardContent class="space-y-4">
            <div class="grid grid-cols-2 gap-4">
              <div class="space-y-2">
                <Label for="new-email">Email</Label>
                <Input
                  id="new-email"
                  v-model="newUser.email"
                  type="email"
                  placeholder="user@company.com"
                />
              </div>
              <div class="space-y-2">
                <Label for="new-password">Пароль</Label>
                <Input
                  id="new-password"
                  v-model="newUser.password"
                  type="password"
                  placeholder="Мін. 8 символів"
                />
              </div>
            </div>
            <div class="space-y-2">
              <Label>Роль</Label>
              <div class="flex gap-2">
                <Button
                  v-for="role in ROLES"
                  :key="role.value"
                  :variant="newUser.role === role.value ? 'default' : 'outline'"
                  size="sm"
                  @click="newUser.role = role.value"
                >
                  {{ role.label }}
                </Button>
              </div>
            </div>
            <div v-if="createError" class="text-sm text-destructive">{{ createError }}</div>
          </CardContent>
          <CardFooter class="gap-2">
            <Button @click="handleCreateUser" :disabled="creating">
              {{ creating ? 'Створення...' : 'Створити' }}
            </Button>
            <Button variant="ghost" @click="showCreateForm = false; createError = ''">
              Скасувати
            </Button>
          </CardFooter>
        </Card>

        <!-- Список користувачів -->
        <Card class="border-border/50 bg-card">
          <CardContent class="p-0">
            <div v-if="loadingUsers" class="p-6 text-center text-muted-foreground">
              Завантаження...
            </div>
            <div v-else-if="users.length === 0" class="p-6 text-center text-muted-foreground">
              Немає користувачів
            </div>
            <div v-else>
              <div
                v-for="(user, index) in users"
                :key="user.id"
                class="flex items-center justify-between px-6 py-4"
                :class="{ 'border-t border-border/30': index > 0 }"
              >
                <div class="flex items-center gap-3">
                  <Avatar class="w-8 h-8">
                    <AvatarFallback class="text-xs bg-secondary">
                      {{ user.email.charAt(0).toUpperCase() }}
                    </AvatarFallback>
                  </Avatar>
                  <div>
                    <div class="text-sm font-medium text-foreground">{{ user.email }}</div>
                    <div class="text-xs text-muted-foreground">
                      {{ new Date(user.created_at).toLocaleDateString('uk-UA') }}
                    </div>
                  </div>
                </div>
                <div class="flex items-center gap-3">
                  <Badge
                    :variant="user.role === 'admin' ? 'default' : 'secondary'"
                    class="text-xs"
                  >
                    {{ user.role }}
                  </Badge>
                  <Badge
                    :variant="user.is_active ? 'outline' : 'destructive'"
                    class="text-xs"
                  >
                    {{ user.is_active ? 'активний' : 'заблокований' }}
                  </Badge>
                  <Button
                    v-if="user.is_active && user.id !== auth.user?.id"
                    variant="ghost"
                    size="sm"
                    class="text-destructive hover:text-destructive h-7"
                    @click="handleDeactivate(user.id)"
                  >
                    Блокувати
                  </Button>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      </section>

    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * AdminView — адмін панель для управління whitelist користувачів.
 *
 * Функціонал:
 *   - Перегляд списку всіх користувачів
 *   - Створення нових користувачів (POST /api/v1/admin/users)
 *   - Деактивація (DELETE /api/v1/admin/users/{id})
 *
 * Admin API Key зберігається в auth store (localStorage).
 * При 401/403 — ключ очищається і відкривається діалог повторного введення.
 */
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardFooter,
} from '@/components/ui/card'
import {
  DialogContent,
  DialogOverlay,
  DialogPortal,
  DialogRoot,
} from 'reka-ui'
import { PlusIcon, ArrowLeftIcon } from 'lucide-vue-next'
import { apiFetch } from '@/api/client'
import type { UserProfile } from '@/api/auth'

const auth = useAuthStore()
const router = useRouter()

const users = ref<UserProfile[]>([])
const loadingUsers = ref(false)
const showCreateForm = ref(false)
const creating = ref(false)
const createError = ref('')

const newUser = ref({ email: '', password: '', role: 'user' })

const ROLES = [
  { value: 'user', label: 'Користувач' },
  { value: 'admin', label: 'Адмін' },
]

// --- Admin API Key Dialog ---

/** Чи відкритий діалог введення ключа */
const showKeyDialog = ref(false)

/** Поточне значення в полі вводу ключа */
const keyInput = ref('')

/** Помилка що відображається у діалозі */
const keyError = ref('')

/**
 * Колбек що буде викликаний після успішного введення ключа.
 * Зберігається щоб відновити операцію яку перервали для введення ключа.
 */
let pendingAction: (() => Promise<void>) | null = null

/**
 * Відкриває діалог введення ключа.
 * Якщо ключ вже є в store — він підставляється в поле (для зручності редагування).
 *
 * @param onSuccess - Функція яку виконати після успішного підтвердження ключа
 */
function openKeyDialog(onSuccess?: () => Promise<void>): void {
  keyInput.value = auth.adminKey
  keyError.value = ''
  pendingAction = onSuccess ?? null
  showKeyDialog.value = true
}

/**
 * Відкриває діалог для зміни ключа вручну (кнопка "Змінити ключ").
 */
function openChangeKey(): void {
  openKeyDialog(async () => {
    await loadUsers()
  })
}

/**
 * Закриває діалог без збереження — повертає на головну якщо ключа немає зовсім.
 */
function handleKeyCancel(): void {
  showKeyDialog.value = false
  keyInput.value = ''
  keyError.value = ''
  pendingAction = null
  // Якщо ключа немає і користувач скасував — не пускаємо в адмінку
  if (!auth.adminKey) {
    router.push('/')
  }
}

/**
 * Запобігає закриттю діалогу кліком поза ним або Escape
 * поки ключ не введено (перший вхід).
 */
function onKeyDialogOpenChange(open: boolean): void {
  if (!open && !auth.adminKey) {
    // Не дозволяємо закрити без ключа
    return
  }
  showKeyDialog.value = open
}

/**
 * Підтверджує введений ключ: зберігає в store та виконує відкладену дію.
 */
async function handleKeySubmit(): Promise<void> {
  const key = keyInput.value.trim()
  if (!key) return

  keyError.value = ''
  auth.setAdminKey(key)
  showKeyDialog.value = false
  keyInput.value = ''

  if (pendingAction) {
    const action = pendingAction
    pendingAction = null
    await action()
  }
}

// --- Admin API helpers ---

/**
 * Виконує admin API запит з поточним ключем зі store.
 * При 401/403 — очищає ключ та відкриває діалог повторного введення.
 *
 * @param fn - Async функція що виконує запит, отримує актуальний ключ
 * @returns true якщо успішно, false якщо запит перервано для введення ключа
 */
async function withAdminKey(fn: (key: string) => Promise<void>): Promise<boolean> {
  // Якщо ключа немає — спочатку попросити
  if (!auth.adminKey) {
    openKeyDialog(async () => { await fn(auth.adminKey) })
    return false
  }

  try {
    await fn(auth.adminKey)
    return true
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e)
    // 401/403 — ключ невірний, скидаємо та просимо знову
    if (msg.includes('401') || msg.includes('403') || msg.toLowerCase().includes('unauthorized')) {
      auth.clearAdminKey()
      keyError.value = 'Невірний ключ. Спробуйте ще раз.'
      openKeyDialog(async () => { await fn(auth.adminKey) })
      return false
    }
    throw e
  }
}

// --- Business logic ---

/**
 * Завантажує список користувачів через admin API (X-API-Key зі store).
 */
async function loadUsers(): Promise<void> {
  loadingUsers.value = true
  try {
    await withAdminKey(async (key) => {
      users.value = await apiFetch<UserProfile[]>('/api/v1/admin/users', {
        headers: { 'X-API-Key': key },
      })
    })
  } catch (e) {
    console.error('Не вдалось завантажити користувачів:', e)
  } finally {
    loadingUsers.value = false
  }
}

/**
 * Створює нового користувача.
 */
async function handleCreateUser(): Promise<void> {
  createError.value = ''
  if (!newUser.value.email || !newUser.value.password) {
    createError.value = 'Email та пароль обовʼязкові'
    return
  }

  creating.value = true
  try {
    await withAdminKey(async (key) => {
      const created = await apiFetch<UserProfile>('/api/v1/admin/users', {
        method: 'POST',
        body: JSON.stringify(newUser.value),
        headers: { 'X-API-Key': key },
      })
      users.value.push(created)
      showCreateForm.value = false
      newUser.value = { email: '', password: '', role: 'user' }
    })
  } catch (e) {
    createError.value = e instanceof Error ? e.message : 'Помилка створення'
  } finally {
    creating.value = false
  }
}

/**
 * Деактивує користувача.
 */
async function handleDeactivate(userId: string): Promise<void> {
  if (!confirm('Заблокувати цього користувача?')) return

  try {
    await withAdminKey(async (key) => {
      await apiFetch(`/api/v1/admin/users/${userId}`, {
        method: 'DELETE',
        headers: { 'X-API-Key': key },
      })
      const user = users.value.find(u => u.id === userId)
      if (user) user.is_active = false
    })
  } catch (e) {
    alert(e instanceof Error ? e.message : 'Помилка деактивації')
  }
}

onMounted(loadUsers)
</script>
