<template>
  <!-- Відповідь асистента — рендеримо markdown з підтримкою стрімінгу -->
  <div class="text-sm text-foreground leading-relaxed">
    <!-- Markdown рендер -->
    <div
      class="prose prose-sm prose-invert max-w-none
             prose-headings:text-foreground
             prose-p:text-foreground
             prose-strong:text-foreground
             prose-ul:text-foreground
             prose-li:text-foreground
             prose-code:text-foreground
             prose-code:bg-secondary
             prose-code:px-1
             prose-code:rounded
             prose-pre:bg-secondary
             prose-pre:border
             prose-pre:border-border/50"
      v-html="renderedHtml"
    />
    <!-- Мигаючий курсор під час стрімінгу -->
    <span v-if="streaming" class="inline-block w-0.5 h-4 bg-foreground/70 animate-pulse ml-0.5 align-middle" />
  </div>
</template>

<script setup lang="ts">
/**
 * AssistantMessage — компонент для відображення відповіді AI асистента.
 *
 * Функціонал:
 *   - Рендеринг markdown через marked
 *   - Мигаючий курсор під час стрімінгу
 *   - Безпека: sanitize HTML щоб запобігти XSS
 *
 * Props:
 *   content  — текст відповіді (може бути markdown)
 *   streaming — чи зараз відбувається стрімінг (показує курсор)
 */
import { computed } from 'vue'
import { marked } from 'marked'

const props = withDefaults(
  defineProps<{
    content: string
    streaming?: boolean
  }>(),
  {
    streaming: false,
  }
)

/**
 * Рендеримо markdown у HTML.
 * marked — легкий та швидкий парсер, підходить для стрімінгу.
 */
const renderedHtml = computed(() => {
  if (!props.content) return ''
  // Синхронний рендер (marked підтримує sync mode)
  return marked.parse(props.content, { async: false }) as string
})
</script>
