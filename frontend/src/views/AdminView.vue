<template>
  <!-- Адміністративна панель — управління користувачами та системою -->
  <div class="min-h-screen bg-background">
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
      <Badge variant="outline" class="text-xs text-muted-foreground">
        {{ auth.user?.email }}
      </Badge>
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
 * Захищений: лише role="admin" + JWT (router guard)
 */
import { ref, onMounted } from 'vue'
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
import { PlusIcon, ArrowLeftIcon } from 'lucide-vue-next'
import { apiFetch } from '@/api/client'
import type { UserProfile } from '@/api/auth'

const auth = useAuthStore()

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

/**
 * Завантажує список користувачів через admin API (X-API-Key).
 * Використовується при монтуванні компонента.
 */
async function loadUsers() {
  loadingUsers.value = true
  try {
    const adminKey = prompt('Введіть Admin API Key:') ?? ''
    users.value = await apiFetch<UserProfile[]>('/api/v1/admin/users', {
      headers: { 'X-API-Key': adminKey },
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
async function handleCreateUser() {
  createError.value = ''
  if (!newUser.value.email || !newUser.value.password) {
    createError.value = 'Email та пароль обовʼязкові'
    return
  }

  creating.value = true
  try {
    const adminKey = prompt('Введіть Admin API Key:') ?? ''
    const created = await apiFetch<UserProfile>('/api/v1/admin/users', {
      method: 'POST',
      body: JSON.stringify(newUser.value),
      headers: { 'X-API-Key': adminKey },
    })
    users.value.push(created)
    showCreateForm.value = false
    newUser.value = { email: '', password: '', role: 'user' }
  } catch (e) {
    createError.value = e instanceof Error ? e.message : 'Помилка створення'
  } finally {
    creating.value = false
  }
}

/**
 * Деактивує користувача.
 */
async function handleDeactivate(userId: string) {
  if (!confirm('Заблокувати цього користувача?')) return

  try {
    const adminKey = prompt('Введіть Admin API Key:') ?? ''
    await apiFetch(`/api/v1/admin/users/${userId}`, {
      method: 'DELETE',
      headers: { 'X-API-Key': adminKey },
    })
    const user = users.value.find(u => u.id === userId)
    if (user) user.is_active = false
  } catch (e) {
    alert(e instanceof Error ? e.message : 'Помилка деактивації')
  }
}

onMounted(loadUsers)
</script>
