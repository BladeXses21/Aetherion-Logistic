<template>
  <!-- Сторінка логіну — мінімалістичний дизайн у стилі Grok AI -->
  <div class="min-h-screen bg-background flex items-center justify-center p-4">
    <div class="w-full max-w-sm space-y-8">

      <!-- Логотип та заголовок -->
      <div class="text-center space-y-2">
        <div class="flex items-center justify-center gap-2 mb-6">
          <div class="w-8 h-8 rounded-lg bg-primary flex items-center justify-center">
            <span class="text-primary-foreground font-bold text-sm">A</span>
          </div>
          <span class="text-xl font-semibold text-foreground">Aetherion</span>
        </div>
        <h1 class="text-2xl font-bold text-foreground">Увійдіть</h1>
        <p class="text-muted-foreground text-sm">AI-асистент для пошуку вантажів</p>
      </div>

      <!-- Форма логіну -->
      <form @submit.prevent="handleLogin" class="space-y-4">
        <!-- Email -->
        <div class="space-y-2">
          <Label for="email">Email</Label>
          <Input
            id="email"
            v-model="email"
            type="email"
            placeholder="your@email.com"
            :disabled="loading"
            autocomplete="email"
            required
          />
        </div>

        <!-- Пароль -->
        <div class="space-y-2">
          <Label for="password">Пароль</Label>
          <Input
            id="password"
            v-model="password"
            type="password"
            placeholder="••••••••"
            :disabled="loading"
            autocomplete="current-password"
            required
          />
        </div>

        <!-- Помилка -->
        <div v-if="errorMessage" class="text-sm text-destructive bg-destructive/10 px-3 py-2 rounded-md">
          {{ errorMessage }}
        </div>

        <!-- Кнопка входу -->
        <Button
          type="submit"
          class="w-full"
          :disabled="loading || !email || !password"
        >
          <span v-if="loading" class="flex items-center gap-2">
            <div class="w-4 h-4 border-2 border-primary-foreground/30 border-t-primary-foreground rounded-full animate-spin" />
            Вхід...
          </span>
          <span v-else>Увійти</span>
        </Button>
      </form>

    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * LoginView — сторінка автентифікації.
 *
 * Після успішного логіну редіректить на початкову сторінку
 * або на маршрут що передано через query param redirect.
 */
import { ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()

const email = ref('')
const password = ref('')
const loading = ref(false)
const errorMessage = ref('')

/**
 * Обробляє сабміт форми логіну.
 * При помилці відображає errorMessage.
 */
async function handleLogin() {
  errorMessage.value = ''
  loading.value = true

  try {
    await auth.login(email.value, password.value)
    // Редірект на початкову сторінку (або де хотів потрапити користувач)
    const redirect = (route.query.redirect as string) ?? '/'
    await router.push(redirect)
  } catch (e) {
    errorMessage.value = e instanceof Error
      ? e.message
      : 'Невірний email або пароль'
  } finally {
    loading.value = false
  }
}
</script>
